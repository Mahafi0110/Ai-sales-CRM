"""AI features: qualify a lead and draft follow-up emails.

The AI only ever sees records the logged-in person may see (the same checks as every page), it only
suggests (nothing is changed or sent without a person), and every use is written to the audit log.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai import prompts, runner
from app.ai.llm import get_llm, model_name
from app.ai.schemas import EmailDraftResult, QualificationResult
from app.models.crm import EmailDraft, Lead, OPEN_STAGES
from app.models.user import User
from app.core.config import get_settings
from app.services import (access, audit_service, customer_service, email_service, knowledge_service,
                          lead_service, opportunity_service)

MAX_FIELD = 1500  # keep prompts small: long notes are cut


def _clip(value, limit: int = MAX_FIELD) -> str:
    text = str(value or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "") if text else "-"


def _lead_context(lead: Lead) -> str:
    return "\n".join([
        f"Name: {_clip(lead.name, 120)}", f"Company: {_clip(lead.company, 160)}", f"Email: {_clip(lead.email, 255)}",
        f"Phone: {_clip(lead.phone, 40)}", f"Source: {_clip(lead.source, 60)}", f"Current status: {lead.status}",
        f"Notes: {_clip(lead.notes)}",
    ])


def _customer_context(db: Session, user: User, customer) -> str:
    lines = [f"Name: {_clip(customer.name, 120)}", f"Company: {_clip(customer.company, 160)}",
             f"Industry: {_clip(customer.industry, 80)}", f"Notes: {_clip(customer.notes)}", "Recent history:"]
    history = customer_service.list_interactions(db, user, customer.id)[:5]
    lines += [f"- {i.created_at:%Y-%m-%d} {i.type}: {_clip(i.summary, 300)}" for i in history] or ["- none"]
    deals = [o for o in opportunity_service.list_opportunities(db, user, customer_id=customer.id)
             if o.stage in {s.value for s in OPEN_STAGES}]
    lines.append("Open deals:")
    lines += [f"- {_clip(o.title, 120)} ({o.stage}, value {o.value})" for o in deals[:5]] or ["- none"]
    return "\n".join(lines)


# ---------- lead qualification ----------
def qualify_lead(db: Session, user: User, lead_id: int, request: Request | None = None) -> Lead:
    lead = lead_service.get_lead(db, user, lead_id)  # permission check comes first
    knowledge, sources = knowledge_service.knowledge_context(
        db, f"ideal customer profile qualification criteria {lead.company or ''} {lead.source or ''} "
            f"{_clip(lead.notes, 200) if lead.notes else ''}", limit=3)
    result = runner.run_json(get_llm(), prompts.QUALIFY_SYSTEM, prompts.QUALIFY_HUMAN,
                             {"lead_data": _lead_context(lead), "knowledge": knowledge}, QualificationResult)
    lead.score = result.score
    lead.ai_analysis = {**result.model_dump(), "model": model_name(), "knowledge_sources": sources,
                        "analyzed_at": datetime.now(timezone.utc).isoformat()}
    db.commit()
    db.refresh(lead)
    audit_service.log_action(db, "ai_lead_qualified", user.id, "lead", lead.id,
                             {"score": result.score, "recommended": result.recommended_status,
                              "model": model_name()}, request)
    return lead


# ---------- email drafts ----------
def _write_draft(db: Session, user: User, *, lead_id=None, customer_id=None, to_email, context: str,
                 goal: str | None, tone: str, knowledge_query: str, request: Request | None) -> EmailDraft:
    if tone not in prompts.TONES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tone must be friendly, formal or brief")
    goal_text = (goal or "").strip() or prompts.DEFAULT_GOAL
    knowledge, _ = knowledge_service.knowledge_context(db, f"{goal_text} {knowledge_query}"[:500], limit=3)
    result = runner.run_json(get_llm(), prompts.EMAIL_SYSTEM, prompts.EMAIL_HUMAN,
                             {"sender": user.full_name, "goal": goal_text, "tone": prompts.TONES[tone],
                              "context": context, "knowledge": knowledge}, EmailDraftResult)
    draft = EmailDraft(lead_id=lead_id, customer_id=customer_id, to_email=to_email, subject=result.subject.strip(),
                       body=result.body.replace("\\n", "\n").strip(), goal=goal_text, ai_model=model_name(),
                       created_by_id=user.id)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    audit_service.log_action(db, "ai_email_drafted", user.id, "email_draft", draft.id,
                             {"lead_id": lead_id, "customer_id": customer_id, "model": model_name()}, request)
    return draft


def draft_email_for_lead(db: Session, user: User, lead_id: int, goal: str | None, tone: str,
                         request: Request | None = None) -> EmailDraft:
    lead = lead_service.get_lead(db, user, lead_id)
    return _write_draft(db, user, lead_id=lead.id, to_email=lead.email, context=_lead_context(lead),
                        goal=goal, tone=tone, knowledge_query=f"{lead.company or ''} {_clip(lead.notes, 200) if lead.notes else ''}",
                        request=request)


def draft_email_for_customer(db: Session, user: User, customer_id: int, goal: str | None, tone: str,
                             request: Request | None = None) -> EmailDraft:
    customer = customer_service.get_customer(db, user, customer_id)
    return _write_draft(db, user, customer_id=customer.id, to_email=customer.email,
                        context=_customer_context(db, user, customer), goal=goal, tone=tone,
                        knowledge_query=f"{customer.company or ''} {customer.industry or ''}", request=request)


def list_drafts(db: Session, user: User, view: str = "draft") -> list[EmailDraft]:
    """view: draft (default), sent, discarded or all."""
    stmt = select(EmailDraft)
    if not access.is_manager(user):
        stmt = stmt.where(EmailDraft.created_by_id == user.id)
    if view != "all":
        stmt = stmt.where(EmailDraft.status == view)
    return list(db.scalars(stmt.order_by(EmailDraft.created_at.desc(), EmailDraft.id.desc())))


def get_draft(db: Session, user: User, draft_id: int) -> EmailDraft:
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise access.not_found("Email draft")
    if not access.is_manager(user) and draft.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this record")
    return draft


def update_draft(db: Session, user: User, draft_id: int, changes: dict, request: Request | None = None) -> EmailDraft:
    draft = get_draft(db, user, draft_id)
    if draft.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This draft was {draft.status} and can no longer be edited")
    for field, value in changes.items():
        setattr(draft, field, value)
    db.commit()
    db.refresh(draft)
    audit_service.log_action(db, "email_draft_edited", user.id, "email_draft", draft.id, {"fields": list(changes)}, request)
    return draft


def discard_draft(db: Session, user: User, draft_id: int, request: Request | None = None) -> EmailDraft:
    draft = get_draft(db, user, draft_id)
    if draft.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This email is already {draft.status}, so it cannot be discarded.")
    draft.status = "discarded"
    db.commit()
    db.refresh(draft)
    audit_service.log_action(db, "email_draft_discarded", user.id, "email_draft", draft.id, None, request)
    return draft


def send_draft(db: Session, user: User, draft_id: int, request: Request | None = None,
               expected: dict | None = None) -> EmailDraft:
    """Really send a draft (or log it, with the console backend). `expected` is what a person approved:
    if the draft changed since, nothing is sent. The same code path is used for a person clicking Send
    and for an approved AI proposal."""
    settings = get_settings()
    draft = get_draft(db, user, draft_id)
    if draft.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This email was already {draft.status}.")
    if not draft.to_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a recipient in the To box before sending.")
    if expected and (draft.to_email, draft.subject, draft.body) != (expected["to"], expected["subject"], expected["body"]):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "The draft was edited after it was submitted for approval. Please review it again.")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    sent_recently = db.scalar(select(func.count(EmailDraft.id)).where(
        EmailDraft.created_by_id == draft.created_by_id, EmailDraft.status == "sent", EmailDraft.sent_at >= since)) or 0
    if sent_recently >= settings.email_max_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"The limit of {settings.email_max_per_hour} emails per hour was reached. Try again later.")
    # Claim the draft first so a double click (or two people) can never send it twice.
    claimed = db.execute(update(EmailDraft).where(EmailDraft.id == draft.id, EmailDraft.status == "draft")
                         .values(status="sending"))
    db.commit()
    if claimed.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already being sent.")
    reply_to = draft.created_by.email if draft.created_by else None
    try:
        via = email_service.send_email(to=draft.to_email, subject=draft.subject, body=draft.body, reply_to=reply_to)
    except Exception:
        db.execute(update(EmailDraft).where(EmailDraft.id == draft.id).values(status="draft"))
        db.commit()
        raise
    draft.status, draft.sent_at, draft.sent_via = "sent", datetime.now(timezone.utc), via
    db.commit()
    db.refresh(draft)
    audit_service.log_action(db, "email_sent", user.id, "email_draft", draft.id,
                             {"to": draft.to_email, "via": via, "lead_id": draft.lead_id,
                              "customer_id": draft.customer_id}, request)
    return draft
