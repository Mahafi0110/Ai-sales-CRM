from datetime import date

from fastapi import HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.crm import Task, TaskStatus
from app.models.user import User
from app.schemas.crm import TaskCreate
from app.services import access, audit_service, customer_service, lead_service, opportunity_service


def visible_tasks(user: User):
    """A query for the tasks this user may see: their own (assigned or created); managers see all."""
    stmt = select(Task)
    if access.is_manager(user):
        return stmt
    return stmt.where(or_(Task.assigned_to_id == user.id, Task.created_by_id == user.id))


def list_tasks(db: Session, user: User, status_filter: str | None = None, overdue_only: bool = False,
               limit: int = 200, offset: int = 0) -> list[Task]:
    stmt = visible_tasks(user)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    if overdue_only:
        stmt = stmt.where(Task.status == TaskStatus.OPEN.value, Task.due_date < date.today())
    stmt = stmt.order_by(Task.due_date.is_(None), Task.due_date, Task.id).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def tasks_for(db: Session, user: User, lead_id: int | None = None, customer_id: int | None = None,
              opportunity_id: int | None = None) -> list[Task]:
    """Open tasks linked to one lead, customer or opportunity (that the user may see)."""
    stmt = visible_tasks(user).where(Task.status == TaskStatus.OPEN.value)
    if lead_id:
        stmt = stmt.where(Task.lead_id == lead_id)
    if customer_id:
        stmt = stmt.where(Task.customer_id == customer_id)
    if opportunity_id:
        stmt = stmt.where(Task.opportunity_id == opportunity_id)
    return list(db.scalars(stmt.order_by(Task.due_date.is_(None), Task.due_date, Task.id)))


def get_task(db: Session, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise access.not_found("Task")
    if not access.is_manager(user) and user.id not in (task.assigned_to_id, task.created_by_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this record")
    return task


def create_task(db: Session, user: User, data: TaskCreate, request: Request | None = None) -> Task:
    # Make sure the user may touch whatever the task is linked to.
    if data.lead_id:
        lead_service.get_lead(db, user, data.lead_id)
    if data.customer_id:
        customer_service.get_customer(db, user, data.customer_id)
    if data.opportunity_id:
        opportunity_service.get_opportunity(db, user, data.opportunity_id)
    assignee = data.assigned_to_id if (data.assigned_to_id and access.is_manager(user)) else user.id
    task = Task(**data.model_dump(exclude={"assigned_to_id"}), assigned_to_id=assignee, created_by_id=user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    audit_service.log_action(db, "task_created", user.id, "task", task.id, {"title": task.title}, request)
    return task


def set_done(db: Session, user: User, task_id: int, done: bool, request: Request | None = None) -> Task:
    task = get_task(db, user, task_id)
    task.status = TaskStatus.DONE.value if done else TaskStatus.OPEN.value
    db.commit()
    db.refresh(task)
    audit_service.log_action(db, "task_completed" if done else "task_reopened", user.id, "task", task.id, None, request)
    return task
