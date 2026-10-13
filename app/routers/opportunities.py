from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.crm import (OpportunityCreate, OpportunityOut, OpportunityUpdate, PipelineSummaryOut, StageUpdate)
from app.services import opportunity_service

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/pipeline/summary", response_model=PipelineSummaryOut)
def pipeline_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return opportunity_service.pipeline_summary(db, user)


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(stage: str | None = None, customer_id: int | None = None, limit: int = 200, offset: int = 0,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return opportunity_service.list_opportunities(db, user, stage, customer_id, min(limit, 500), offset)


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(data: OpportunityCreate, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return opportunity_service.create_opportunity(db, user, data, request)


@router.get("/opportunities/{opp_id}", response_model=OpportunityOut)
def get_opportunity(opp_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return opportunity_service.get_opportunity(db, user, opp_id)


@router.patch("/opportunities/{opp_id}", response_model=OpportunityOut)
def update_opportunity(opp_id: int, data: OpportunityUpdate, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return opportunity_service.update_opportunity(db, user, opp_id, data, request)


@router.post("/opportunities/{opp_id}/stage", response_model=OpportunityOut)
def move_stage(opp_id: int, data: StageUpdate, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    return opportunity_service.move_stage(db, user, opp_id, data.stage, request)
