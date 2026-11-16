from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.accounts.auth_service import psychologist_id_for_session
from app.accounts.security import csrf_token_matches
from app.core.config import settings
from app.core.database import get_db


def get_current_psychologist_id(request: Request, session: Session = Depends(get_db)) -> UUID:
    """Resolve a psychologist only from a live opaque server-side session cookie."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    psychologist_id = psychologist_id_for_session(session, raw_token)
    if psychologist_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Psychologist authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin", "").rstrip("/")
        if (
            not settings.csrf_secret_key
            or origin not in settings.cors_allowed_origins
            or not csrf_token_matches(
                raw_token or "", settings.csrf_secret_key, request.headers.get("x-csrf-token")
            )
        ):
            raise HTTPException(status_code=403, detail="CSRF validation failed")
    return psychologist_id
