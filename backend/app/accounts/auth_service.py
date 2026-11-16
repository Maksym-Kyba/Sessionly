"""OAuth and server-side session use cases for psychologist accounts."""

from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from urllib.parse import urlencode
from uuid import UUID

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import repository
from app.accounts.models import AuthSession, GoogleIdentity, OAuthTransaction, Psychologist
from app.accounts.security import (
    create_pkce_pair,
    decrypt_secret,
    encrypt_secret,
    random_token,
    sha256_hex,
)
from app.core.config import Settings

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
OAUTH_TRANSACTION_TTL = timedelta(minutes=10)
GOOGLE_CERTIFICATE_FETCH_TIMEOUT = 8.0


class GoogleRequestWithTimeout(GoogleRequest):
    """Apply a finite timeout to the Google certificate-key fetch during ID-token checks."""

    def __call__(self, *args, timeout=GOOGLE_CERTIFICATE_FETCH_TIMEOUT, **kwargs):
        return super().__call__(*args, timeout=timeout, **kwargs)


class OAuthNotConfigured(Exception):
    pass


class InvalidOAuthTransaction(Exception):
    pass


class AccountLinkRequired(Exception):
    pass


def _require_oauth_settings(settings: Settings) -> tuple[str, str, str, str]:
    if (
        not settings.google_client_id
        or not settings.google_client_secret
        or not settings.google_redirect_uri
        or not settings.oauth_state_encryption_key
        or not settings.csrf_secret_key
        or not settings.frontend_auth_success_url
        or not settings.frontend_auth_error_url
    ):
        raise OAuthNotConfigured
    return (
        settings.google_client_id,
        settings.google_client_secret,
        settings.google_redirect_uri,
        settings.oauth_state_encryption_key,
    )


def begin_google_login(session: Session, settings: Settings) -> tuple[str, str]:
    client_id, _, redirect_uri, encryption_key = _require_oauth_settings(settings)
    state = random_token()
    browser_binding = random_token()
    nonce = random_token()
    verifier, challenge = create_pkce_pair()
    now = datetime.now(UTC)
    repository.delete_expired_oauth_transactions(session, now)
    transaction = OAuthTransaction(
        state_hash=sha256_hex(state),
        browser_binding_hash=sha256_hex(browser_binding),
        nonce_hash=sha256_hex(nonce),
        pkce_verifier_encrypted=encrypt_secret(encryption_key, verifier),
        expires_at=now + OAUTH_TRANSACTION_TTL,
    )
    repository.add_oauth_transaction(session, transaction)
    session.commit()
    parameters = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
    }
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(parameters)}", browser_binding


def consume_google_transaction(
    session: Session, settings: Settings, state: str, browser_binding: str | None
) -> tuple[str, str]:
    _, _, _, encryption_key = _require_oauth_settings(settings)
    transaction = repository.get_oauth_transaction_for_update(session, sha256_hex(state))
    now = datetime.now(UTC)
    if (
        transaction is None
        or transaction.consumed_at is not None
        or transaction.expires_at <= now
        or not browser_binding
        or not compare_digest(transaction.browser_binding_hash, sha256_hex(browser_binding))
    ):
        session.rollback()
        raise InvalidOAuthTransaction
    try:
        verifier = decrypt_secret(encryption_key, transaction.pkce_verifier_encrypted)
    except ValueError as exc:
        session.rollback()
        raise InvalidOAuthTransaction from exc
    nonce_hash = transaction.nonce_hash
    transaction.consumed_at = now
    session.commit()
    return verifier, nonce_hash


def exchange_and_verify_google_code(
    settings: Settings, code: str, verifier: str, expected_nonce_hash: str
) -> dict[str, object]:
    client_id, client_secret, redirect_uri, _ = _require_oauth_settings(settings)
    try:
        response = httpx.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        token_response = response.json()
        raw_id_token = token_response["id_token"]
        claims = id_token.verify_oauth2_token(raw_id_token, GoogleRequestWithTimeout(), client_id)
    except Exception as exc:
        # Do not propagate provider response bodies or tokens into API errors or logs.
        raise InvalidOAuthTransaction from exc
    if (
        not isinstance(claims, dict)
        or not claims.get("sub")
        or not claims.get("email")
        or claims.get("email_verified") not in (True, "true")
        or sha256_hex(str(claims.get("nonce", ""))) != expected_nonce_hash
    ):
        raise InvalidOAuthTransaction
    return claims


def find_or_create_psychologist(
    session: Session, claims: dict[str, object], default_time_zone: str
) -> Psychologist:
    subject = str(claims["sub"])
    email = str(claims["email"]).strip().lower()
    identity = repository.get_google_identity(session, subject)
    if identity is not None:
        psychologist = repository.get_by_id(session, identity.psychologist_id)
        if psychologist is None:
            raise AccountLinkRequired
        return psychologist

    existing_email_account = repository.get_by_email(session, email)
    if existing_email_account is not None:
        session.rollback()
        raise AccountLinkRequired

    display_name_claim = claims.get("name")
    if not isinstance(display_name_claim, str) or not display_name_claim.strip():
        session.rollback()
        raise AccountLinkRequired
    try:
        psychologist = Psychologist(
            display_name=display_name_claim.strip()[:200],
            email=email,
            time_zone=default_time_zone,
        )
        repository.add_psychologist(session, psychologist)
        repository.add_google_identity(
            session,
            GoogleIdentity(
                psychologist_id=psychologist.id,
                google_subject=subject,
                email_at_link_time=email,
            ),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        concurrent_identity = repository.get_google_identity(session, subject)
        if concurrent_identity is not None:
            psychologist = repository.get_by_id(session, concurrent_identity.psychologist_id)
            if psychologist is not None:
                return psychologist
        raise AccountLinkRequired from exc
    return psychologist


def create_session(session: Session, psychologist_id: UUID, settings: Settings) -> str:
    raw_token = random_token()
    repository.add_auth_session(
        session,
        AuthSession(
            psychologist_id=psychologist_id,
            session_token_hash=sha256_hex(raw_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        ),
    )
    session.commit()
    return raw_token


def psychologist_id_for_session(session: Session, raw_token: str | None) -> UUID | None:
    if not raw_token:
        return None
    auth_session = repository.get_active_session(session, sha256_hex(raw_token), datetime.now(UTC))
    if auth_session is None:
        session.rollback()
        return None
    psychologist_id = auth_session.psychologist_id
    session.rollback()
    return psychologist_id


def revoke_session(session: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    auth_session = repository.get_session_by_token_hash(session, sha256_hex(raw_token))
    if auth_session is not None and auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(UTC)
        session.commit()
    else:
        session.rollback()
