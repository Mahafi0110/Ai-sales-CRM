from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.agent import service
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.agent import AgentRunOut, AgentRunRequest

router = APIRouter(prefix="/api/agent", tags=["assistant"])


@router.post("/run", response_model=AgentRunOut, status_code=status.HTTP_201_CREATED)
def run(data: AgentRunRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.run_agent(db, user, data.message, request)


@router.get("/runs", response_model=list[AgentRunOut])
def runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.list_runs(db, user)


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.get_run(db, user, run_id)
