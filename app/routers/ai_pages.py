"""HTML pages for the AI features: qualify a lead, draft emails, review drafts."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.prompts import TONES
from app.core.database import get_db
from app.core.deps import page_user
from app.models.user import User
from app.routers.crm_pages import back, blank, error_text
from app.routers.pages import render
from app.schemas.ai import EmailDraftUpdate
from app.services import ai_service

router = APIRouter(include_in_schema=False)


@router.post("/leads/{lead_id}/qualify")
def lead_qualify(lead_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        ai_service.qualify_lead(db, user, lead_id, request)
    except HTTPException as exc:
        return back(f"/leads/{lead_id}", error=error_text(exc))
    return back(f"/leads/{lead_id}", msg="AI assessment is ready")


@router.post("/leads/{lead_id}/email-draft")
def lead_email_draft(lead_id: int, request: Request, goal: str = Form(""), tone: str = Form("friendly"),
                     user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        draft = ai_service.draft_email_for_lead(db, user, lead_id, blank(goal), tone, request)
    except HTTPException as exc:
        return back(f"/leads/{lead_id}", error=error_text(exc))
    return back(f"/emails/{draft.id}", msg="Draft written. Please read and edit it before using it.")


@router.post("/customers/{customer_id}/email-draft")
def customer_email_draft(customer_id: int, request: Request, goal: str = Form(""), tone: str = Form("friendly"),
                         user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        draft = ai_service.draft_email_for_customer(db, user, customer_id, blank(goal), tone, request)
    except HTTPException as exc:
        return back(f"/customers/{customer_id}", error=error_text(exc))
    return back(f"/emails/{draft.id}", msg="Draft written. Please read and edit it before using it.")


@router.get("/emails", response_class=HTMLResponse)
def emails_page(request: Request, view: str = "draft", user: User = Depends(page_user), db: Session = Depends(get_db)):
    view = "sent" if view == "sent" else "draft"
    return render(request, "emails.html", user, active="emails", view=view,
                  drafts=ai_service.list_drafts(db, user, view))


@router.get("/emails/{draft_id}", response_class=HTMLResponse)
def email_detail(draft_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    return render(request, "email_detail.html", user, active="emails", draft=ai_service.get_draft(db, user, draft_id))


@router.post("/emails/{draft_id}/edit")
def email_edit(draft_id: int, request: Request, to_email: str = Form(""), subject: str = Form(""),
               body: str = Form(""), user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = EmailDraftUpdate(to_email=blank(to_email), subject=subject.strip(), body=body.strip())
        ai_service.update_draft(db, user, draft_id, data.model_dump(exclude_unset=True), request)
    except (ValidationError, HTTPException) as exc:
        return back(f"/emails/{draft_id}", error=error_text(exc))
    return back(f"/emails/{draft_id}", msg="Draft saved")


@router.post("/emails/{draft_id}/discard")
def email_discard(draft_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        ai_service.discard_draft(db, user, draft_id, request)
    except HTTPException as exc:
        return back(f"/emails/{draft_id}", error=error_text(exc))
    return back("/emails", msg="Draft discarded")


@router.post("/emails/{draft_id}/send")
def email_send(draft_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        draft = ai_service.send_draft(db, user, draft_id, request)
    except HTTPException as exc:
        return back(f"/emails/{draft_id}", error=error_text(exc))
    note = ("Logged only: EMAIL_BACKEND is 'console', so nothing was really delivered."
            if draft.sent_via == "console" else "Email sent.")
    return back(f"/emails/{draft_id}", msg=note)
