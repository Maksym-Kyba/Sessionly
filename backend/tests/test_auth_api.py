from datetime import UTC, datetime, timedelta
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import AuthSession, GoogleIdentity, OAuthTransaction, Psychologist
from app.accounts import auth_service
from app.accounts.auth_service import create_session, psychologist_id_for_session, revoke_session
from app.accounts.security import sha256_hex
from app.availability.models import AvailabilitySlot
from app.core.config import Settings, settings


def configure_oauth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")
    monkeypatch.setattr(
        settings,
        "google_redirect_uri",
        "http://localhost:8000/api/v1/auth/google/callback",
    )
    monkeypatch.setattr(settings, "frontend_auth_success_url", "http://localhost:3000/")
    monkeypatch.setattr(settings, "frontend_auth_error_url", "http://localhost:3000/")
    monkeypatch.setattr(settings, "frontend_auth_redirect_allowlist", ["http://localhost:3000/"])
    monkeypatch.setattr(settings, "oauth_state_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "csrf_secret_key", "test-csrf-secret-long-enough-32chars")
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    monkeypatch.setattr(settings, "session_cookie_samesite", "lax")
    monkeypatch.setattr(settings, "session_cookie_name", "sessionly_session")
    monkeypatch.setattr(settings, "oauth_browser_cookie_name", "sessionly_oauth_browser")
    monkeypatch.setattr(settings, "session_ttl_seconds", 604800)


def test_production_cookie_and_redirect_defaults_are_secure() -> None:
    production = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:password@localhost/sessionly",
        app_env="production",
        google_redirect_uri="https://api.example.test/api/v1/auth/google/callback",
        frontend_auth_success_url="https://app.example.test/auth/success",
        frontend_auth_error_url="https://app.example.test/auth/error",
        frontend_auth_redirect_allowlist=[
            "https://app.example.test/auth/success",
            "https://app.example.test/auth/error",
        ],
        cors_allowed_origins=["https://app.example.test"],
        client_verification_secret_key="test-client-verification-secret-value-32",
        client_verification_link_base_url="https://app.example.test/verify-email",
    )
    assert production.session_cookie_secure is True
    assert production.session_cookie_name.startswith("__Host-")
    assert production.oauth_browser_cookie_name.startswith("__Host-")
    assert production.session_cookie_path == "/"
    assert production.oauth_browser_cookie_path == "/"

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:password@localhost/sessionly",
            app_env="production",
            session_cookie_secure=False,
            session_cookie_name="sessionly_session",
            oauth_browser_cookie_name="sessionly_oauth",
            google_redirect_uri="https://api.example.test/api/v1/auth/google/callback",
            frontend_auth_success_url="https://app.example.test/",
            frontend_auth_error_url="https://app.example.test/",
            frontend_auth_redirect_allowlist=["https://app.example.test/"],
            cors_allowed_origins=["https://app.example.test"],
        )


@pytest.mark.anyio
async def test_oauth_start_creates_hashed_single_use_state_and_pkce(
    api_client, database_engine, monkeypatch
) -> None:
    configure_oauth(monkeypatch)
    response = await api_client.get("/api/v1/auth/google/start")

    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    assert "calendar" not in query["scope"][0]
    assert "code_verifier" not in response.headers["location"]

    state = query["state"][0]
    browser_binding = response.cookies.get(settings.oauth_browser_cookie_name)
    assert browser_binding
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "max-age=600" in response.headers["set-cookie"].lower()
    assert "path=/api/v1/auth/google" in response.headers["set-cookie"].lower()
    with Session(database_engine) as session:
        transaction = session.scalar(
            select(OAuthTransaction).where(OAuthTransaction.state_hash == sha256_hex(state))
        )
        assert transaction is not None
        assert transaction.browser_binding_hash == sha256_hex(browser_binding)
        with pytest.raises(auth_service.InvalidOAuthTransaction):
            auth_service.consume_google_transaction(
                session, settings, state, "different-browser-binding"
            )
        verifier, nonce_hash = auth_service.consume_google_transaction(
            session, settings, state, browser_binding
        )
        assert verifier
        assert nonce_hash == transaction.nonce_hash
        with pytest.raises(auth_service.InvalidOAuthTransaction):
            auth_service.consume_google_transaction(session, settings, state, browser_binding)


@pytest.mark.anyio
async def test_callback_creates_account_cookie_me_and_logout(
    api_client, database_engine, monkeypatch
) -> None:
    configure_oauth(monkeypatch)
    started = await api_client.get("/api/v1/auth/google/start")
    query = parse_qs(urlsplit(started.headers["location"]).query)
    claims = {
        "sub": "google-subject-1",
        "email": "psychologist@example.test",
        "email_verified": True,
        "name": "Dr Example",
        "nonce": query["nonce"][0],
    }
    monkeypatch.setattr(
        "app.accounts.router.exchange_and_verify_google_code",
        lambda *args: claims,
    )

    callback = await api_client.get(
        "/api/v1/auth/google/callback",
        params={"code": "test-code", "state": query["state"][0]},
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:3000/"
    cookie = callback.cookies.get(settings.session_cookie_name)
    assert cookie
    cookie_header = callback.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    assert "path=/api/v1" in cookie_header
    assert "secure" not in cookie_header

    factory_session = Session(database_engine)
    try:
        psychologist = factory_session.scalar(
            select(Psychologist).where(Psychologist.email == "psychologist@example.test")
        )
        identity = factory_session.scalar(
            select(GoogleIdentity).where(GoogleIdentity.google_subject == "google-subject-1")
        )
        auth_session = factory_session.scalar(select(AuthSession))
        assert psychologist is not None and identity is not None and auth_session is not None
        assert identity.psychologist_id == psychologist.id
        assert auth_session.session_token_hash == sha256_hex(cookie)
        assert auth_session.session_token_hash != cookie
        assert abs((auth_session.expires_at - auth_session.created_at).total_seconds() - 604800) < 2
    finally:
        factory_session.close()

    api_client.cookies.set(settings.session_cookie_name, cookie, domain="testserver")
    me = await api_client.get("/api/v1/accounts/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Dr Example"
    csrf = me.json()["csrf_token"]

    protected = await api_client.get("/api/v1/accounts/me/availability-rules")
    assert protected.status_code == 200
    invalid_csrf = await api_client.post(
        "/api/v1/accounts/me/availability-rules",
        json={},
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": "invalid"},
    )
    assert invalid_csrf.status_code == 403
    invalid_origin = await api_client.post(
        "/api/v1/accounts/me/availability-rules",
        json={},
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
    )
    assert invalid_origin.status_code == 403
    create_rule = await api_client.post(
        "/api/v1/accounts/me/availability-rules",
        json={
            "weekday": 0,
            "local_start": "09:00:00",
            "local_end": "12:00:00",
            "session_duration_minutes": 50,
            "price_minor": 120000,
            "currency": "UAH",
            "valid_from": "2027-01-04",
            "valid_until": None,
        },
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": csrf},
    )
    assert create_rule.status_code == 201

    logout = await api_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": csrf},
    )
    assert logout.status_code == 204
    assert "httponly" in logout.headers["set-cookie"].lower()
    assert (await api_client.get("/api/v1/accounts/me")).status_code == 401


@pytest.mark.anyio
async def test_oauth_state_is_one_time_and_email_collision_is_not_linked(
    api_client, database_engine, psychologist, monkeypatch
) -> None:
    configure_oauth(monkeypatch)
    started = await api_client.get("/api/v1/auth/google/start")
    query = parse_qs(urlsplit(started.headers["location"]).query)
    claims = {
        "sub": "different-google-subject",
        "email": psychologist.email,
        "email_verified": True,
        "name": "Unlinked User",
        "nonce": query["nonce"][0],
    }
    monkeypatch.setattr(
        "app.accounts.router.exchange_and_verify_google_code",
        lambda *args: claims,
    )
    callback_url = "/api/v1/auth/google/callback"
    first = await api_client.get(
        callback_url, params={"code": "test-code", "state": query["state"][0]}
    )
    assert first.status_code == 303
    assert "auth_error=account_unavailable" in first.headers["location"]
    replay = await api_client.get(
        callback_url, params={"code": "test-code", "state": query["state"][0]}
    )
    assert replay.status_code == 303
    assert "auth_error=oauth_failed" in replay.headers["location"]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(GoogleIdentity)) == 0
        assert session.scalar(select(func.count()).select_from(Psychologist)) == 1


@pytest.mark.anyio
async def test_expired_oauth_state_is_rejected(api_client, database_engine, monkeypatch) -> None:
    configure_oauth(monkeypatch)
    started = await api_client.get("/api/v1/auth/google/start")
    query = parse_qs(urlsplit(started.headers["location"]).query)
    with Session(database_engine) as session:
        transaction = session.scalar(
            select(OAuthTransaction).where(
                OAuthTransaction.state_hash == sha256_hex(query["state"][0])
            )
        )
        assert transaction is not None
        transaction.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    callback = await api_client.get(
        "/api/v1/auth/google/callback",
        params={"code": "unused-code", "state": query["state"][0]},
    )
    assert callback.status_code == 303
    assert "auth_error=oauth_failed" in callback.headers["location"]
    assert not callback.cookies.get(settings.session_cookie_name)


@pytest.mark.anyio
async def test_missing_session_and_missing_csrf_fail_closed(api_client, monkeypatch) -> None:
    configure_oauth(monkeypatch)
    assert (await api_client.get("/api/v1/accounts/me")).status_code == 401
    assert (await api_client.get("/api/v1/accounts/me/availability-rules")).status_code == 401


@pytest.mark.anyio
async def test_oauth_start_is_unavailable_until_required_secrets_are_configured(
    api_client, monkeypatch
) -> None:
    for field in (
        "google_client_id",
        "google_client_secret",
        "google_redirect_uri",
        "oauth_state_encryption_key",
        "csrf_secret_key",
        "frontend_auth_success_url",
        "frontend_auth_error_url",
    ):
        monkeypatch.setattr(settings, field, None)
    response = await api_client.get("/api/v1/auth/google/start")
    assert response.status_code == 503


def test_google_id_token_verification_checks_signature_claims_and_pkce(monkeypatch) -> None:
    configure_oauth(monkeypatch)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_signer = crypt.RSASigner.from_string(
        other_private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        key_id="test-kid",
    )

    def fake_google_request():
        def request(*args, **kwargs):
            return SimpleNamespace(
                status=200,
                data=json.dumps({"test-kid": public_pem}).encode(),
            )

        return request

    monkeypatch.setattr(auth_service, "GoogleRequestWithTimeout", fake_google_request)
    posted: dict[str, object] = {}

    def fake_post(url, *, data, timeout):
        posted.update(data)
        posted["timeout"] = timeout
        return _FakeTokenResponse(posted["id_token"])

    monkeypatch.setattr(auth_service.httpx, "post", fake_post)
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "sub": "google-subject-2",
        "email": "psychologist@example.test",
        "email_verified": True,
        "name": "Dr Example",
        "nonce": "expected-nonce",
        "iss": "https://accounts.google.com",
        "aud": "test-client-id",
        "iat": now,
        "exp": now + 120,
    }

    def sign(payload, signer=None):
        selected_signer = signer or crypt.RSASigner.from_string(private_pem, key_id="test-kid")
        posted["id_token"] = jwt.encode(selected_signer, payload)

    expected_nonce_hash = sha256_hex("expected-nonce")
    sign(claims)
    assert (
        auth_service.exchange_and_verify_google_code(
            settings, "code", "verifier", expected_nonce_hash
        )
        == claims
    )
    assert posted["code_verifier"] == "verifier"
    assert posted["timeout"] == 8.0

    invalid_claims = [
        {**claims, "aud": "another-client"},
        {**claims, "iss": "https://attacker.example"},
        {**claims, "exp": now - 1},
        {**claims, "nonce": "wrong-nonce"},
        {**claims, "email_verified": False},
    ]
    for invalid in invalid_claims:
        sign(invalid)
        with pytest.raises(auth_service.InvalidOAuthTransaction):
            auth_service.exchange_and_verify_google_code(
                settings, "code", "verifier", expected_nonce_hash
            )

    sign(claims, signer=other_signer)
    with pytest.raises(auth_service.InvalidOAuthTransaction):
        auth_service.exchange_and_verify_google_code(
            settings, "code", "verifier", expected_nonce_hash
        )


class _FakeTokenResponse:
    def __init__(self, id_token: str | bytes) -> None:
        self.id_token = id_token

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str | bytes]:
        return {"id_token": self.id_token}


@pytest.mark.anyio
async def test_public_profile_does_not_invent_price_or_duration(api_client, psychologist) -> None:
    response = await api_client.get(f"/api/v1/psychologists/{psychologist.public_id}")
    assert response.status_code == 200
    assert response.json() == {
        "public_id": psychologist.public_id,
        "display_name": psychologist.display_name,
        "time_zone": psychologist.time_zone,
        "session_duration_minutes": None,
        "price_minor": None,
        "currency": None,
    }


@pytest.mark.anyio
async def test_public_profile_returns_shared_terms_only_when_unambiguous(
    api_client, database_engine, psychologist
) -> None:
    start = datetime.now(UTC) + timedelta(days=2)
    with Session(database_engine) as session:
        session.add_all(
            [
                AvailabilitySlot(
                    psychologist_id=psychologist.id,
                    starts_at=start,
                    ends_at=start + timedelta(minutes=50),
                    price_minor=120000,
                    currency="UAH",
                    state="published",
                ),
                AvailabilitySlot(
                    psychologist_id=psychologist.id,
                    starts_at=start + timedelta(hours=1),
                    ends_at=start + timedelta(hours=1, minutes=50),
                    price_minor=120000,
                    currency="UAH",
                    state="published",
                ),
            ]
        )
        session.commit()

    response = await api_client.get(f"/api/v1/psychologists/{psychologist.public_id}")
    assert response.json()["session_duration_minutes"] == 50
    assert response.json()["price_minor"] == 120000
    assert response.json()["currency"] == "UAH"

    with Session(database_engine) as session:
        session.add(
            AvailabilitySlot(
                psychologist_id=psychologist.id,
                starts_at=start + timedelta(hours=2),
                ends_at=start + timedelta(hours=3),
                price_minor=150000,
                currency="UAH",
                state="published",
            )
        )
        session.commit()

    ambiguous = await api_client.get(f"/api/v1/psychologists/{psychologist.public_id}")
    assert ambiguous.json()["session_duration_minutes"] is None
    assert ambiguous.json()["price_minor"] is None
    assert ambiguous.json()["currency"] is None


def test_multiple_sessions_are_independent_and_expire(database_engine, psychologist, monkeypatch):
    configure_oauth(monkeypatch)
    with Session(database_engine) as session:
        first_token = create_session(session, psychologist.id, settings)
        second_token = create_session(session, psychologist.id, settings)
        assert first_token != second_token
        assert psychologist_id_for_session(session, first_token) == psychologist.id
        assert psychologist_id_for_session(session, second_token) == psychologist.id

        revoke_session(session, first_token)
        assert psychologist_id_for_session(session, first_token) is None
        assert psychologist_id_for_session(session, second_token) == psychologist.id

        second_session = session.scalar(
            select(AuthSession).where(AuthSession.session_token_hash == sha256_hex(second_token))
        )
        assert second_session is not None
        second_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        assert psychologist_id_for_session(session, second_token) is None


def test_existing_google_subject_resolves_existing_psychologist(database_engine, monkeypatch):
    configure_oauth(monkeypatch)
    claims = {
        "sub": "stable-google-subject",
        "email": "psychologist@example.test",
        "email_verified": True,
        "name": "Dr Example",
    }
    with Session(database_engine) as session:
        first = auth_service.find_or_create_psychologist(session, claims, "Europe/Kyiv")
        first_id = first.id
        second = auth_service.find_or_create_psychologist(session, claims, "Europe/Kyiv")
        assert second.id == first_id
        assert session.scalar(select(func.count()).select_from(Psychologist)) == 1
        assert session.scalar(select(func.count()).select_from(GoogleIdentity)) == 1


def test_concurrent_first_login_creates_one_psychologist(database_engine, monkeypatch):
    configure_oauth(monkeypatch)
    barrier = Barrier(2)
    both_checked_for_email = Barrier(2)
    claims = {
        "sub": "concurrent-google-subject",
        "email": "concurrent@example.test",
        "email_verified": True,
        "name": "Dr Concurrent",
    }
    original_get_by_email = auth_service.repository.get_by_email

    def get_by_email_after_both_checked(session, email):
        result = original_get_by_email(session, email)
        both_checked_for_email.wait(timeout=5)
        return result

    monkeypatch.setattr(auth_service.repository, "get_by_email", get_by_email_after_both_checked)

    def login_once():
        with Session(database_engine) as session:
            barrier.wait(timeout=5)
            psychologist = auth_service.find_or_create_psychologist(session, claims, "Europe/Kyiv")
            return psychologist.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        psychologist_ids = list(executor.map(lambda _: login_once(), range(2)))

    assert psychologist_ids[0] == psychologist_ids[1]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Psychologist)) == 1
        assert session.scalar(select(func.count()).select_from(GoogleIdentity)) == 1


def test_first_login_does_not_publish_email_local_part_if_google_has_no_name(
    database_engine, monkeypatch
):
    configure_oauth(monkeypatch)
    claims = {
        "sub": "subject-without-name",
        "email": "olena.koval@example.test",
        "email_verified": True,
    }
    with Session(database_engine) as session:
        with pytest.raises(auth_service.AccountLinkRequired):
            auth_service.find_or_create_psychologist(session, claims, "Europe/Kyiv")
        assert session.scalar(select(func.count()).select_from(Psychologist)) == 0
