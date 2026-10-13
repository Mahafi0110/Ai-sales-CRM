from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.crm import Customer, Interaction
from app.models.user import User
from app.schemas.crm import CustomerCreate, CustomerUpdate, InteractionCreate
from app.services import access, audit_service


def list_customers(db: Session, user: User, q: str | None = None, limit: int = 100, offset: int = 0) -> list[Customer]:
    stmt = access.scope(select(Customer), user, Customer.owner_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.email.ilike(like), Customer.company.ilike(like)))
    return list(db.scalars(stmt.order_by(Customer.created_at.desc(), Customer.id.desc()).limit(limit).offset(offset)))


def get_customer(db: Session, user: User, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise access.not_found("Customer")
    access.ensure_access(user, customer.owner_id)
    return customer


def create_customer(db: Session, user: User, data: CustomerCreate, request: Request | None = None) -> Customer:
    owner_id = data.owner_id if (data.owner_id and access.is_manager(user)) else user.id
    customer = Customer(**data.model_dump(exclude={"owner_id"}), owner_id=owner_id)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    audit_service.log_action(db, "customer_created", user.id, "customer", customer.id, {"name": customer.name}, request)
    return customer


def update_customer(db: Session, user: User, customer_id: int, data: CustomerUpdate,
                    request: Request | None = None) -> Customer:
    customer = get_customer(db, user, customer_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    audit_service.log_action(db, "customer_updated", user.id, "customer", customer.id, {"fields": list(changes)}, request)
    return customer


def add_interaction(db: Session, user: User, customer_id: int, data: InteractionCreate,
                    request: Request | None = None) -> Interaction:
    customer = get_customer(db, user, customer_id)
    item = Interaction(customer_id=customer.id, type=data.type.value, summary=data.summary, created_by_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    audit_service.log_action(db, "interaction_added", user.id, "customer", customer.id, {"type": item.type}, request)
    return item


def list_interactions(db: Session, user: User, customer_id: int) -> list[Interaction]:
    customer = get_customer(db, user, customer_id)
    return list(db.scalars(select(Interaction).where(Interaction.customer_id == customer.id)
                           .order_by(Interaction.created_at.desc(), Interaction.id.desc())))
