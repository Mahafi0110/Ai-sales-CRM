"""Create the first admin user.  Usage: python -m scripts.create_admin you@example.com "Your Name" "password" """
import sys

from app import models  # noqa: F401
from app.core.database import SessionLocal
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services import user_service


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit('Usage: python -m scripts.create_admin EMAIL "FULL NAME" PASSWORD')
    email, name, password = sys.argv[1:]
    with SessionLocal() as db:
        if user_service.get_by_email(db, email):
            sys.exit("That email already exists.")
        user = user_service.create_user(db, UserCreate(email=email, full_name=name, password=password, role=Role.ADMIN))
        print(f"Created admin {user.email} (id {user.id})")


if __name__ == "__main__":
    main()
