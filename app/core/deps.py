"""Reusable FastAPI dependencies: current user and role checks."""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import Role, User

COOKIE_NAME = "access_token"


class LoginRequired(Exception):
    """Raised by HTML pages when nobody is logged in; main.py turns it into a redirect to /login."""


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return request.cookies.get(COOKIE_NAME)


def get_current_user_or_none(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _token_from_request(request)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None


def get_current_user(user: User | None = Depends(get_current_user_or_none)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_roles(*roles: Role):
    """Build a dependency that only lets the given roles through."""
    allowed = {r.value for r in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user

    return checker


def page_user(user: User | None = Depends(get_current_user_or_none)) -> User:
    if user is None:
        raise LoginRequired()
    return user
