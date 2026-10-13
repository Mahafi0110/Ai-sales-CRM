from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.ai import AIStatusOut, DraftRequest, EmailDraftOut, EmailDraftUpdate
from app.schemas.crm import LeadOut
from app.services import ai_service

router = APIRouter(prefix="/api", tags=["ai"])


@router.get("/ai/status", response_model=AIStatusOut)
def ai_status(_: User = Depends(get_current_user)):
    return {"configured": llm.is_configured(), "provider": get_settings().llm_provider, "model": llm.model_name()}


@router.post("/leads/{lead_id}/qualify", response_model=LeadOut)
def qualify_lead(lead_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ai_service.qualify_lead(db, user, lead_id, request)


@router.post("/leads/{lead_id}/email-draft", response_model=EmailDraftOut, status_code=status.HTTP_201_CREATED)
def draft_for_lead(lead_id: int, data: DraftRequest, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return ai_service.draft_email_for_lead(db, user, lead_id, data.goal, data.tone, request)


@router.post("/customers/{customer_id}/email-draft", response_model=EmailDraftOut, status_code=status.HTTP_201_CREATED)
def draft_for_customer(customer_id: int, data: DraftRequest, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return ai_service.draft_email_for_customer(db, user, customer_id, data.goal, data.tone, request)


@router.get("/email-drafts", response_model=list[EmailDraftOut])
def list_drafts(view: str = "draft", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ai_service.list_drafts(db, user, view)


@router.get("/email-drafts/{draft_id}", response_model=EmailDraftOut)
def get_draft(draft_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ai_service.get_draft(db, user, draft_id)


@router.patch("/email-drafts/{draft_id}", response_model=EmailDraftOut)
def update_draft(draft_id: int, data: EmailDraftUpdate, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return ai_service.update_draft(db, user, draft_id, data.model_dump(exclude_unset=True), request)


@router.post("/email-drafts/{draft_id}/discard", response_model=EmailDraftOut)
def discard_draft(draft_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ai_service.discard_draft(db, user, draft_id, request)


@router.post("/email-drafts/{draft_id}/send", response_model=EmailDraftOut)
def send_draft(draft_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ai_service.send_draft(db, user, draft_id, request)
