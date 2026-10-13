from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.crm import (CustomerCreate, CustomerOut, CustomerUpdate, InteractionCreate, InteractionOut)
from app.services import customer_service

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(q: str | None = None, limit: int = 100, offset: int = 0,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return customer_service.list_customers(db, user, q, min(limit, 500), offset)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(data: CustomerCreate, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return customer_service.create_customer(db, user, data, request)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return customer_service.get_customer(db, user, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, data: CustomerUpdate, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return customer_service.update_customer(db, user, customer_id, data, request)


@router.get("/{customer_id}/interactions", response_model=list[InteractionOut])
def list_interactions(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return customer_service.list_interactions(db, user, customer_id)


@router.post("/{customer_id}/interactions", response_model=InteractionOut, status_code=status.HTTP_201_CREATED)
def add_interaction(customer_id: int, data: InteractionCreate, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return customer_service.add_interaction(db, user, customer_id, data, request)
