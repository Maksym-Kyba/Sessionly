from uuid import UUID

from fastapi import HTTPException, Request, status


def get_current_psychologist_id(request: Request) -> UUID:
    """Return the authenticated psychologist set by future OAuth middleware.

    No request header or development credential is trusted here. Until Google OAuth supplies a
    verified principal on request.state, protected endpoints reject the request.
    """
    psychologist_id = getattr(request.state, "psychologist_id", None)
    if psychologist_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Psychologist authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return UUID(str(psychologist_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated principal",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
