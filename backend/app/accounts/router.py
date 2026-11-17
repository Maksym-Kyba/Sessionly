from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.accounts import api
from app.accounts import service
from app.accounts.auth_service import (
    AccountLinkRequired,
    InvalidOAuthTransaction,
    OAuthNotConfigured,
    begin_google_login,
    consume_google_transaction,
    create_session,
    exchange_and_verify_google_code,
    find_or_create_psychologist,
    revoke_session,
)
from app.accounts.dependencies import get_current_psychologist_id
from app.accounts.schemas import PsychologistMeRead, PsychologistProfileUpdate
from app.accounts.security import csrf_token
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/api/v1", tags=["accounts"])


def _redirect(url: str, *, error: str | None = None) -> RedirectResponse:
    if url not in settings.frontend_auth_redirect_allowlist:
        raise HTTPException(status_code=503, detail="Authentication redirect is not configured")
    if error is None:
        target = url
    else:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["auth_error"] = error
        target = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/google/start", include_in_schema=True)
def google_start(session: Session = Depends(get_db)) -> RedirectResponse:
    try:
        authorization_url, browser_binding = begin_google_login(session, settings)
    except OAuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="OAuth configuration is invalid") from exc
    response = RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.set_cookie(
        key=settings.oauth_browser_cookie_name,
        value=browser_binding,
        max_age=600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=settings.oauth_browser_cookie_path,
    )
    return response


def _oauth_error_redirect(error_code: str) -> RedirectResponse:
    response = _redirect(settings.frontend_auth_error_url or "", error=error_code)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        key=settings.oauth_browser_cookie_name,
        path=settings.oauth_browser_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/auth/google/callback", include_in_schema=True)
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_db),
) -> Response:
    if not state:
        return _oauth_error_redirect("oauth_failed")
    try:
        verifier, expected_nonce_hash = consume_google_transaction(
            session,
            settings,
            state,
            request.cookies.get(settings.oauth_browser_cookie_name),
        )
    except (InvalidOAuthTransaction, OAuthNotConfigured):
        return _oauth_error_redirect("oauth_failed")
    if error or not code:
        return _oauth_error_redirect("sign_in_cancelled")
    try:
        claims = exchange_and_verify_google_code(settings, code, verifier, expected_nonce_hash)
        psychologist = find_or_create_psychologist(
            session, claims, settings.default_psychologist_time_zone
        )
        psychologist_id: UUID = psychologist.id
        raw_token = create_session(session, psychologist_id, settings)
    except AccountLinkRequired:
        return _oauth_error_redirect("account_unavailable")
    except (InvalidOAuthTransaction, OAuthNotConfigured):
        return _oauth_error_redirect("oauth_failed")
    except (SQLAlchemyError, ValueError, TypeError, KeyError):
        session.rollback()
        return _oauth_error_redirect("oauth_failed")

    redirect = _redirect(settings.frontend_auth_success_url or "")
    redirect.headers["Cache-Control"] = "no-store"
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )
    redirect.delete_cookie(
        key=settings.oauth_browser_cookie_name,
        path=settings.oauth_browser_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return redirect


@router.get("/accounts/me", response_model=PsychologistMeRead)
def get_me(
    request: Request,
    response: Response,
    psychologist_id: UUID = Depends(get_current_psychologist_id),
    session: Session = Depends(get_db),
) -> PsychologistMeRead:
    response.headers["Cache-Control"] = "no-store"
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token or not settings.csrf_secret_key:
        raise HTTPException(status_code=503, detail="Session security is not configured")
    psychologist = api.psychologist_by_id(session, psychologist_id)
    if psychologist is None:
        raise HTTPException(status_code=401, detail="Psychologist authentication required")
    return PsychologistMeRead(
        public_id=psychologist.public_id,
        display_name=psychologist.display_name,
        email=psychologist.email,
        time_zone=psychologist.time_zone,
        csrf_token=csrf_token(raw_token, settings.csrf_secret_key),
    )


@router.patch("/accounts/me", response_model=PsychologistMeRead)
def update_me(
    data: PsychologistProfileUpdate,
    request: Request,
    response: Response,
    psychologist_id: UUID = Depends(get_current_psychologist_id),
    session: Session = Depends(get_db),
) -> PsychologistMeRead:
    response.headers["Cache-Control"] = "no-store"
    try:
        psychologist = service.update_psychologist_profile(
            session, psychologist_id, data.model_dump(exclude_unset=True)
        )
    except LookupError as exc:
        raise HTTPException(status_code=401, detail="Psychologist authentication required") from exc
    if psychologist is None:
        raise HTTPException(status_code=401, detail="Psychologist authentication required")
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token or not settings.csrf_secret_key:
        raise HTTPException(status_code=503, detail="Session security is not configured")
    return PsychologistMeRead(
        public_id=psychologist.public_id,
        display_name=psychologist.display_name,
        email=psychologist.email,
        time_zone=psychologist.time_zone,
        csrf_token=csrf_token(raw_token, settings.csrf_secret_key),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    session: Session = Depends(get_db),
    _: UUID = Depends(get_current_psychologist_id),
) -> Response:
    revoke_session(session, request.cookies.get(settings.session_cookie_name))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    return response
