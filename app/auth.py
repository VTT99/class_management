"""Optional bearer-token auth. When API_BEARER_TOKEN is empty, auth is disabled."""

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    token = get_settings().api_bearer_token
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
