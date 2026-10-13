from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.crm import DashboardOut, TaskCreate, TaskOut
from app.services import dashboard_service, task_service

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(status: str | None = None, overdue: bool = False, limit: int = 200, offset: int = 0,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return task_service.list_tasks(db, user, status, overdue, min(limit, 500), offset)


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return task_service.create_task(db, user, data, request)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return task_service.set_done(db, user, task_id, True, request)


@router.post("/tasks/{task_id}/reopen", response_model=TaskOut)
def reopen_task(task_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return task_service.set_done(db, user, task_id, False, request)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return dashboard_service.get_stats(db, user)
