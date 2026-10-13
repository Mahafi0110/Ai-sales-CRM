from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.crm import Customer, Interaction, Lead, LeadStatus
from app.models.user import User
from app.schemas.crm import LeadCreate, LeadUpdate
from app.services import access, audit_service


def list_leads(db: Session, user: User, q: str | None = None, status_filter: str | None = None,
               owner_id: int | None = None, limit: int = 100, offset: int = 0) -> list[Lead]:
    stmt = access.scope(select(Lead), user, Lead.owner_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Lead.name.ilike(like), Lead.email.ilike(like), Lead.company.ilike(like)))
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    if owner_id and access.is_manager(user):
        stmt = stmt.where(Lead.owner_id == owner_id)
    return list(db.scalars(stmt.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit).offset(offset)))


def stale_leads(db: Session, user: User, days: int = 7, limit: int = 20) -> list[Lead]:
    """Open leads nobody has touched for `days` days, oldest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    open_statuses = [LeadStatus.NEW.value, LeadStatus.CONTACTED.value, LeadStatus.QUALIFIED.value]
    stmt = access.scope(select(Lead), user, Lead.owner_id).where(Lead.status.in_(open_statuses),
                                                                    Lead.updated_at < cutoff)
    return list(db.scalars(stmt.order_by(Lead.updated_at.asc(), Lead.id).limit(limit)))


def get_lead(db: Session, user: User, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise access.not_found("Lead")
    access.ensure_access(user, lead.owner_id)
    return lead


def create_lead(db: Session, user: User, data: LeadCreate, request: Request | None = None) -> Lead:
    # Sales reps always own the leads they create; managers may pick an owner.
    owner_id = data.owner_id if (data.owner_id and access.is_manager(user)) else user.id
    lead = Lead(**data.model_dump(exclude={"owner_id"}), owner_id=owner_id)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    audit_service.log_action(db, "lead_created", user.id, "lead", lead.id, {"name": lead.name}, request)
    return lead


def update_lead(db: Session, user: User, lead_id: int, data: LeadUpdate, request: Request | None = None) -> Lead:
    lead = get_lead(db, user, lead_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(lead, field, value)
    db.commit()
    db.refresh(lead)
    audit_service.log_action(db, "lead_updated", user.id, "lead", lead.id, {"fields": list(changes)}, request)
    return lead


def set_status(db: Session, user: User, lead_id: int, new_status: LeadStatus, request: Request | None = None) -> Lead:
    lead = get_lead(db, user, lead_id)
    if lead.status == LeadStatus.CONVERTED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "This lead is already converted to a customer")
    if new_status == LeadStatus.CONVERTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use the convert action to turn a lead into a customer")
    old = lead.status
    lead.status = new_status.value
    db.commit()
    db.refresh(lead)
    audit_service.log_action(db, "lead_status_changed", user.id, "lead", lead.id,
                             {"from": old, "to": lead.status}, request)
    return lead


def assign_lead(db: Session, user: User, lead_id: int, owner_id: int, request: Request | None = None) -> Lead:
    access.ensure_manager(user)
    if not db.get(User, owner_id):
        raise access.not_found("User")
    lead = get_lead(db, user, lead_id)
    old = lead.owner_id
    lead.owner_id = owner_id
    db.commit()
    db.refresh(lead)
    audit_service.log_action(db, "lead_assigned", user.id, "lead", lead.id, {"from": old, "to": owner_id}, request)
    return lead


def convert_to_customer(db: Session, user: User, lead_id: int, request: Request | None = None) -> Customer:
    lead = get_lead(db, user, lead_id)
    if lead.status == LeadStatus.CONVERTED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "This lead is already converted")
    customer = Customer(name=lead.name, email=lead.email, phone=lead.phone, company=lead.company,
                        notes=lead.notes, owner_id=lead.owner_id)
    db.add(customer)
    db.flush()
    db.add(Interaction(customer_id=customer.id, type="note", created_by_id=user.id,
                       summary=f"Converted from lead (source: {lead.source or 'unknown'})."))
    lead.status = LeadStatus.CONVERTED.value
    lead.customer_id = customer.id
    db.commit()
    db.refresh(customer)
    audit_service.log_action(db, "lead_converted", user.id, "lead", lead.id, {"customer_id": customer.id}, request)
    return customer
