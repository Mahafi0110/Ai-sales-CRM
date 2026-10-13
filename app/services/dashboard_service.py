from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm import Customer, Lead, LeadStatus, Task, TaskStatus
from app.models.user import User
from app.services import access, approval_service, opportunity_service, task_service

OPEN_LEAD_STATUSES = [LeadStatus.NEW.value, LeadStatus.CONTACTED.value, LeadStatus.QUALIFIED.value]


def get_stats(db: Session, user: User) -> dict:
    lead_stmt = access.scope(select(Lead.status, func.count(Lead.id)).group_by(Lead.status), user, Lead.owner_id)
    leads_by_status = {status: count for status, count in db.execute(lead_stmt)}

    customer_count = db.scalar(access.scope(select(func.count(Customer.id)), user, Customer.owner_id))

    visible = task_service.visible_tasks(user).subquery()
    open_tasks = db.scalar(select(func.count()).select_from(visible).where(visible.c.status == TaskStatus.OPEN.value))
    overdue_tasks = db.scalar(select(func.count()).select_from(visible).where(
        visible.c.status == TaskStatus.OPEN.value, visible.c.due_date < date.today()))

    pipeline = opportunity_service.pipeline_summary(db, user)
    recent_leads = list(db.scalars(access.scope(select(Lead), user, Lead.owner_id)
                                   .order_by(Lead.created_at.desc(), Lead.id.desc()).limit(5)))
    upcoming_tasks = task_service.list_tasks(db, user, status_filter=TaskStatus.OPEN.value, limit=5)

    return {
        "open_leads": sum(leads_by_status.get(s, 0) for s in OPEN_LEAD_STATUSES),
        "leads_by_status": leads_by_status,
        "customers": customer_count or 0,
        "open_opportunities": pipeline["open_count"],
        "pipeline_value": pipeline["open_value"],
        "won_value": pipeline["won_value"],
        "win_rate": pipeline["win_rate"],
        "open_tasks": open_tasks or 0,
        "overdue_tasks": overdue_tasks or 0,
        "pending_approvals": approval_service.count_pending(db, user),
        "recent_leads": recent_leads,
        "upcoming_tasks": upcoming_tasks,
    }
