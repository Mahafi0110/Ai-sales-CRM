from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm import CLOSED_STAGES, OPEN_STAGES, Opportunity, Stage
from app.models.user import User
from app.schemas.crm import OpportunityCreate, OpportunityUpdate
from app.services import access, audit_service, customer_service

PIPELINE_ORDER = [s.value for s in Stage]


def list_opportunities(db: Session, user: User, stage: str | None = None, customer_id: int | None = None,
                       limit: int = 200, offset: int = 0) -> list[Opportunity]:
    stmt = access.scope(select(Opportunity), user, Opportunity.owner_id)
    if stage:
        stmt = stmt.where(Opportunity.stage == stage)
    if customer_id:
        stmt = stmt.where(Opportunity.customer_id == customer_id)
    return list(db.scalars(stmt.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()).limit(limit).offset(offset)))


def get_opportunity(db: Session, user: User, opp_id: int) -> Opportunity:
    opp = db.get(Opportunity, opp_id)
    if not opp:
        raise access.not_found("Opportunity")
    access.ensure_access(user, opp.owner_id)
    return opp


def create_opportunity(db: Session, user: User, data: OpportunityCreate, request: Request | None = None) -> Opportunity:
    customer = customer_service.get_customer(db, user, data.customer_id)  # also checks access
    if access.is_manager(user):
        owner_id = data.owner_id or customer.owner_id or user.id
    else:
        owner_id = user.id
    opp = Opportunity(title=data.title, customer_id=customer.id, value=data.value,
                      expected_close_date=data.expected_close_date, stage=data.stage.value, owner_id=owner_id)
    if data.stage in CLOSED_STAGES:
        opp.closed_at = datetime.now(timezone.utc)
    db.add(opp)
    db.commit()
    db.refresh(opp)
    audit_service.log_action(db, "opportunity_created", user.id, "opportunity", opp.id,
                             {"title": opp.title, "value": str(opp.value)}, request)
    return opp


def update_opportunity(db: Session, user: User, opp_id: int, data: OpportunityUpdate,
                       request: Request | None = None) -> Opportunity:
    opp = get_opportunity(db, user, opp_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(opp, field, value)
    db.commit()
    db.refresh(opp)
    audit_service.log_action(db, "opportunity_updated", user.id, "opportunity", opp.id, {"fields": list(changes)}, request)
    return opp


def move_stage(db: Session, user: User, opp_id: int, new_stage: Stage, request: Request | None = None) -> Opportunity:
    opp = get_opportunity(db, user, opp_id)
    old = opp.stage
    opp.stage = new_stage.value
    opp.closed_at = datetime.now(timezone.utc) if new_stage in CLOSED_STAGES else None
    db.commit()
    db.refresh(opp)
    audit_service.log_action(db, "opportunity_stage_changed", user.id, "opportunity", opp.id,
                             {"from": old, "to": opp.stage}, request)
    return opp


def pipeline_summary(db: Session, user: User) -> dict:
    """Counts and money per stage, plus win rate. Used by the pipeline page, the dashboard and (later) the AI."""
    stmt = access.scope(
        select(Opportunity.stage, func.count(Opportunity.id), func.coalesce(func.sum(Opportunity.value), 0))
        .group_by(Opportunity.stage), user, Opportunity.owner_id)
    found = {stage: (count, Decimal(total)) for stage, count, total in db.execute(stmt)}
    stages = [{"stage": s, "count": found.get(s, (0, Decimal(0)))[0], "value": found.get(s, (0, Decimal(0)))[1]}
              for s in PIPELINE_ORDER]
    won, lost = found.get("won", (0, Decimal(0)))[0], found.get("lost", (0, Decimal(0)))[0]
    open_names = [s.value for s in OPEN_STAGES]
    return {
        "stages": stages,
        "open_count": sum(found.get(s, (0, 0))[0] for s in open_names),
        "open_value": sum((found.get(s, (0, Decimal(0)))[1] for s in open_names), Decimal(0)),
        "won_value": found.get("won", (0, Decimal(0)))[1],
        "win_rate": round(won / (won + lost) * 100, 1) if (won + lost) else None,
    }
