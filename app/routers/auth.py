from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import COOKIE_NAME, get_current_user
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import LoginRequest, UserOut
from app.services import audit_service, user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def set_login_cookie(response: Response, user_id: int) -> str:
    settings = get_settings()
    token = create_access_token(user_id)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        secure=settings.cookie_secure, max_age=settings.access_token_expire_minutes * 60,
    )
    return token


@router.post("/login")
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = user_service.authenticate(db, data.email, data.password)
    if not user:
        audit_service.log_action(db, "login_failed", details={"email": data.email}, request=request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    token = set_login_cookie(response, user.id)
    audit_service.log_action(db, "login", user_id=user.id, request=request)
    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/logout")
def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.delete_cookie(COOKIE_NAME)
    audit_service.log_action(db, "logout", user_id=user.id, request=request)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
