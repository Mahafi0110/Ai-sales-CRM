from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models.user import Role, User
from app.schemas.user import UserCreate, UserOut
from app.services import audit_service, user_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_roles(Role.ADMIN))):
    if user_service.get_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = user_service.create_user(db, data)
    audit_service.log_action(db, "user_created", user_id=admin.id, entity_type="user",
                             entity_id=user.id, details={"role": user.role}, request=request)
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER))):
    return db.scalars(select(User).order_by(User.id)).all()
