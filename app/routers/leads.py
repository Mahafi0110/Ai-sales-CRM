from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.crm import AssignRequest, CustomerOut, LeadCreate, LeadOut, LeadStatusUpdate, LeadUpdate
from app.services import lead_service

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=list[LeadOut])
def list_leads(q: str | None = None, status: str | None = None, owner_id: int | None = None,
               limit: int = 100, offset: int = 0,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return lead_service.list_leads(db, user, q, status, owner_id, min(limit, 500), offset)


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return lead_service.create_lead(db, user, data, request)


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return lead_service.get_lead(db, user, lead_id)


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, data: LeadUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return lead_service.update_lead(db, user, lead_id, data, request)


@router.post("/{lead_id}/status", response_model=LeadOut)
def set_status(lead_id: int, data: LeadStatusUpdate, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    return lead_service.set_status(db, user, lead_id, data.status, request)


@router.post("/{lead_id}/assign", response_model=LeadOut)
def assign(lead_id: int, data: AssignRequest, request: Request, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    return lead_service.assign_lead(db, user, lead_id, data.owner_id, request)


@router.post("/{lead_id}/convert", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def convert(lead_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return lead_service.convert_to_customer(db, user, lead_id, request)
