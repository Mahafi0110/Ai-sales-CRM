"""Who may see and change what. Sales reps only see their own records; admins and managers see all."""
from fastapi import HTTPException, status

from app.models.user import Role, User


def is_manager(user: User) -> bool:
    return user.role in (Role.ADMIN.value, Role.MANAGER.value)


def scope(stmt, user: User, owner_column):
    """Limit a query to the records this user is allowed to see."""
    return stmt if is_manager(user) else stmt.where(owner_column == user.id)


def ensure_access(user: User, owner_id: int | None) -> None:
    if not is_manager(user) and owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this record")


def ensure_manager(user: User) -> None:
    if not is_manager(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers and admins can do this")


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")
