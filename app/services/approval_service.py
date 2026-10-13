"""The approval queue: the AI may only PROPOSE sensitive actions; a person decides.

Safety rules built in:
- What will happen is written down (payload) when the proposal is made, and shown to the person before they decide.
- Everything is checked again at the moment of approval (permissions, and whether the record changed meanwhile).
- An approval can run only once (a double click or two people cannot execute it twice).
- Approving is done as the person who clicked, so it uses *their* permissions.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.crm import LeadStatus, Stage
from app.models.user import User
from app.services import access, ai_service, audit_service, lead_service, opportunity_service

log = logging.getLogger(__name__)
WAITING = ("pending", "failed")  # shown on the "Waiting" tab: needs a decision, or a retry


def _title(text: str) -> str:
    return text if len(text) <= 200 else text[:197] + "..."


def _bad(message: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, message)


# ---------- the kinds of action ----------
@dataclass
class ActionSpec:
    label: str
    external: bool  # reaches outside the app (email)
    validate: Callable[[Session, User, dict], tuple[dict, str]]  # -> (payload, title); raises if not allowed
    execute: Callable[[Session, User, ApprovalRequest, Request | None], dict]


def _validate_send_email(db, user, args):
    draft = ai_service.get_draft(db, user, int(args.get("draft_id") or 0))
    if draft.status != "draft":
        raise _bad(f"That email is already {draft.status}.", status.HTTP_409_CONFLICT)
    if not draft.to_email:
        raise _bad("That draft has no recipient. A person must add one first.")
    payload = {"draft_id": draft.id, "to": draft.to_email, "subject": draft.subject, "body": draft.body,
               "lead_id": draft.lead_id, "customer_id": draft.customer_id}
    return payload, _title(f"Send email to {draft.to_email}: {draft.subject}")


def _execute_send_email(db, decider, approval, request):
    draft = ai_service.send_draft(db, decider, approval.payload["draft_id"], request, expected=approval.payload)
    return {"sent_to": draft.to_email, "subject": draft.subject, "via": draft.sent_via}


def _validate_lead_status(db, user, args):
    lead = lead_service.get_lead(db, user, int(args.get("lead_id") or 0))
    try:
        new = LeadStatus(str(args.get("status", "")))
    except ValueError:
        raise _bad("status must be one of: new, contacted, qualified, unqualified") from None
    if new == LeadStatus.CONVERTED or lead.status == LeadStatus.CONVERTED.value:
        raise _bad("Converting a lead to a customer is done with the Convert button, not here.")
    if new.value == lead.status:
        raise _bad(f"The lead is already '{lead.status}'.")
    payload = {"lead_id": lead.id, "lead_name": lead.name, "from": lead.status, "to": new.value}
    return payload, _title(f"Change lead {lead.name}: {lead.status} to {new.value}")


def _execute_lead_status(db, decider, approval, request):
    p = approval.payload
    lead = lead_service.get_lead(db, decider, p["lead_id"])
    if lead.status != p["from"]:
        raise _bad(f"The lead is now '{lead.status}', not '{p['from']}'. Please review it again.", status.HTTP_409_CONFLICT)
    lead_service.set_status(db, decider, lead.id, LeadStatus(p["to"]), request)
    return {"lead_id": lead.id, "status": p["to"]}


def _validate_deal_stage(db, user, args):
    opp = opportunity_service.get_opportunity(db, user, int(args.get("opportunity_id") or 0))
    try:
        new = Stage(str(args.get("stage", "")))
    except ValueError:
        raise _bad("stage must be one of: prospecting, qualification, proposal, negotiation, won, lost") from None
    if new.value == opp.stage:
        raise _bad(f"The deal is already in '{opp.stage}'.")
    payload = {"opportunity_id": opp.id, "title": opp.title, "from": opp.stage, "to": new.value,
               "value": str(opp.value)}
    return payload, _title(f"Move deal {opp.title}: {opp.stage} to {new.value}")


def _execute_deal_stage(db, decider, approval, request):
    p = approval.payload
    opp = opportunity_service.get_opportunity(db, decider, p["opportunity_id"])
    if opp.stage != p["from"]:
        raise _bad(f"The deal is now in '{opp.stage}', not '{p['from']}'. Please review it again.", status.HTTP_409_CONFLICT)
    opportunity_service.move_stage(db, decider, opp.id, Stage(p["to"]), request)
    return {"opportunity_id": opp.id, "stage": p["to"]}


ACTIONS: dict[str, ActionSpec] = {
    "send_email": ActionSpec("Send email", True, _validate_send_email, _execute_send_email),
    "change_lead_status": ActionSpec("Change lead status", False, _validate_lead_status, _execute_lead_status),
    "move_deal_stage": ActionSpec("Move deal", False, _validate_deal_stage, _execute_deal_stage),
}


# ---------- who may do what ----------
def can_decide(user: User, approval: ApprovalRequest) -> bool:
    """The person who asked, or a manager/admin."""
    return access.is_manager(user) or approval.requested_by_id == user.id


def get_approval(db: Session, user: User, approval_id: int) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    if not approval:
        raise access.not_found("Approval")
    if not can_decide(user, approval):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this record")
    return approval


# ---------- proposing ----------
def propose(db: Session, user: User, action_type: str, args: dict, reason: str | None = None,
            run_id: int | None = None, request: Request | None = None) -> ApprovalRequest:
    spec = ACTIONS.get(action_type)
    if spec is None:
        raise _bad(f"Unknown action '{action_type}'.")
    payload, title = spec.validate(db, user, args)  # also checks that this person may touch the record
    for existing in db.scalars(select(ApprovalRequest).where(
            ApprovalRequest.requested_by_id == user.id, ApprovalRequest.action_type == action_type,
            ApprovalRequest.status == "pending")):
        if existing.payload == payload:  # the same request is already waiting: do not pile up copies
            return existing
    approval = ApprovalRequest(requested_by_id=user.id, run_id=run_id, action_type=action_type, title=title,
                               reason=(reason or "").strip()[:500] or None, payload=payload)
    db.add(approval)
    db.commit()
    db.refresh(approval)
    audit_service.log_action(db, "approval_requested", user.id, "approval", approval.id,
                             {"action": action_type, "run_id": run_id}, request)
    return approval


# ---------- listing ----------
def _visible(user: User):
    stmt = select(ApprovalRequest)
    return stmt if access.is_manager(user) else stmt.where(ApprovalRequest.requested_by_id == user.id)


def list_approvals(db: Session, user: User, group: str = "waiting", limit: int = 100) -> list[ApprovalRequest]:
    stmt = _visible(user)
    stmt = (stmt.where(ApprovalRequest.status.in_(WAITING)) if group == "waiting"
            else stmt.where(ApprovalRequest.status.notin_(WAITING)))
    return list(db.scalars(stmt.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc()).limit(limit)))


def count_pending(db: Session, user: User) -> int:
    stmt = _visible(user).where(ApprovalRequest.status == "pending").subquery()
    return db.scalar(select(func.count()).select_from(stmt)) or 0


def for_run(db: Session, user: User, run_id: int) -> list[ApprovalRequest]:
    return list(db.scalars(_visible(user).where(ApprovalRequest.run_id == run_id).order_by(ApprovalRequest.id)))


# ---------- deciding ----------
def approve(db: Session, user: User, approval_id: int, request: Request | None = None) -> ApprovalRequest:
    approval = get_approval(db, user, approval_id)
    spec = ACTIONS[approval.action_type]
    # Claim it first: only one click can ever win, so the action runs at most once.
    claimed = db.execute(update(ApprovalRequest)
                         .where(ApprovalRequest.id == approval.id, ApprovalRequest.status.in_(WAITING))
                         .values(status="approved", decided_by_id=user.id, decided_at=datetime.now(timezone.utc),
                                 error=None))
    db.commit()
    if claimed.rowcount != 1:
        raise _bad("This request was already decided.", status.HTTP_409_CONFLICT)
    db.refresh(approval)
    audit_service.log_action(db, "approval_approved", user.id, "approval", approval.id,
                             {"action": approval.action_type}, request)
    try:
        approval.result = spec.execute(db, user, approval, request)
        approval.status, approval.executed_at = "executed", datetime.now(timezone.utc)
    except HTTPException as exc:
        approval.status, approval.error = "failed", str(exc.detail)
    except Exception:  # never leave it half-done without a record
        log.exception("Approved action crashed")
        approval.status, approval.error = "failed", "Something unexpected went wrong. Nothing was changed."
    db.commit()
    db.refresh(approval)
    audit_service.log_action(db, "approval_executed" if approval.status == "executed" else "approval_failed",
                             user.id, "approval", approval.id,
                             {"action": approval.action_type, "error": approval.error}, request)
    return approval


def reject(db: Session, user: User, approval_id: int, note: str | None = None,
           request: Request | None = None) -> ApprovalRequest:
    approval = get_approval(db, user, approval_id)
    rejected = db.execute(update(ApprovalRequest)
                          .where(ApprovalRequest.id == approval.id, ApprovalRequest.status.in_(WAITING))
                          .values(status="rejected", decided_by_id=user.id, decided_at=datetime.now(timezone.utc),
                                  decision_note=(note or "").strip()[:500] or None))
    db.commit()
    if rejected.rowcount != 1:
        raise _bad("This request was already decided.", status.HTTP_409_CONFLICT)
    db.refresh(approval)
    audit_service.log_action(db, "approval_rejected", user.id, "approval", approval.id,
                             {"action": approval.action_type}, request)
    return approval
