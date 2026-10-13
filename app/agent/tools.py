"""The tools the AI assistant may use.

Every tool calls the same services as the web pages, as the logged-in person, so the assistant can never see or
do more than that person can. Tools only look things up or prepare work (scores, drafts, tasks). Nothing is sent,
deleted or approved. Results are wrapped in <data> tags so the model treats them as information, not orders.
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Literal

from fastapi import HTTPException, Request
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.ai.errors import AIBusy, AINotConfigured
from app.core.config import get_settings
from app.models.crm import LeadStatus, TaskStatus
from app.models.user import User
from app.schemas.crm import TaskCreate
from app.services import (ai_service, approval_service, customer_service, knowledge_service, lead_service,
                          opportunity_service, task_service)

NOTE_LIMIT = 500


@dataclass
class ToolContext:
    db: Session
    user: User
    request: Request | None = None
    run_id: int | None = None
    trace: list = field(default_factory=list)  # what happened, shown to the user afterwards
    tool_calls: int = 0
    ai_actions: int = 0
    proposals: int = 0


# ---------- what each tool accepts ----------
class SearchLeadsArgs(BaseModel):
    query: str = Field("", description="Text to look for in name, email or company. Empty means all.")
    status: str = Field("", description="Only leads with this status: new, contacted, qualified, unqualified or "
                                        "converted. Leave empty for any status.")
    limit: int = Field(10, ge=1, le=20)


class StaleLeadsArgs(BaseModel):
    days: int = Field(7, ge=1, le=90, description="Leads untouched for at least this many days.")
    limit: int = Field(10, ge=1, le=20)


class LeadIdArgs(BaseModel):
    lead_id: int = Field(description="The lead's id number (from search_leads).")


class SearchCustomersArgs(BaseModel):
    query: str = Field("", description="Text to look for in name, email or company. Empty means all.")
    limit: int = Field(10, ge=1, le=20)


class CustomerIdArgs(BaseModel):
    customer_id: int = Field(description="The customer's id number (from search_customers).")


class NoArgs(BaseModel):
    pass


class ListTasksArgs(BaseModel):
    view: Literal["open", "overdue", "done"] = "open"


class DraftEmailArgs(BaseModel):
    lead_id: int | None = Field(None, description="Write to this lead. Use lead_id OR customer_id, not both.")
    customer_id: int | None = Field(None, description="Write to this customer.")
    goal: str = Field("", max_length=300, description="What the email should achieve.")
    tone: Literal["friendly", "formal", "brief"] = "friendly"


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300, description="What to look up in the company documents, "
                                                                "e.g. 'pricing for the starter plan'.")
    limit: int = Field(4, ge=1, le=6)


class RequestSendEmailArgs(BaseModel):
    draft_id: int = Field(description="The id of an existing email draft (from draft_follow_up_email).")
    reason: str = Field("", max_length=300, description="One sentence: why this email should be sent now.")


class RequestLeadStatusArgs(BaseModel):
    lead_id: int = Field(description="The lead's id number.")
    new_status: str = Field(description="One of: new, contacted, qualified, unqualified.")
    reason: str = Field("", max_length=300, description="One sentence: why the status should change.")


class RequestDealStageArgs(BaseModel):
    opportunity_id: int = Field(description="The deal's id number.")
    new_stage: str = Field(description="One of: prospecting, qualification, proposal, negotiation, won, lost.")
    reason: str = Field("", max_length=300, description="One sentence: why the deal should move.")


class CreateTaskArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="Short task title, e.g. 'Call Priya about pricing'.")
    due_in_days: int | None = Field(None, ge=0, le=365, description="Days from today. Omit for no due date.")
    lead_id: int | None = Field(None, description="Link the task to this lead (optional).")
    customer_id: int | None = Field(None, description="Link the task to this customer (optional).")


# ---------- small helpers ----------
def _clip(value, limit: int = 160):
    text = str(value or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "") if text else None


def _days_since(moment: datetime | None) -> int | None:
    if not moment:
        return None
    if moment.tzinfo is None:  # some databases return times without a timezone
        moment = moment.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - moment).days, 0)


def _lead_row(lead) -> dict:
    return {"id": lead.id, "name": lead.name, "company": lead.company, "status": lead.status, "score": lead.score,
            "owner": lead.owner.full_name if lead.owner else None, "days_since_update": _days_since(lead.updated_at)}


def _customer_row(customer) -> dict:
    return {"id": customer.id, "name": customer.name, "company": customer.company, "email": customer.email,
            "industry": customer.industry}


def _task_row(task) -> dict:
    return {"id": task.id, "title": task.title, "due_date": task.due_date, "status": task.status,
            "lead_id": task.lead_id, "customer_id": task.customer_id}


# ---------- the tools (each returns (data, link)) ----------
def build_tools(ctx: ToolContext) -> list[StructuredTool]:
    db, user, request = ctx.db, ctx.user, ctx.request
    settings = get_settings()

    def search_leads(query: str = "", status: str = "", limit: int = 10):
        if status and status not in {s.value for s in LeadStatus}:
            raise HTTPException(400, "status must be one of: new, contacted, qualified, unqualified, converted")
        leads = lead_service.list_leads(db, user, query or None, status or None, None, limit)
        return {"count": len(leads), "leads": [_lead_row(l) for l in leads]}, None

    def find_stale_leads(days: int = 7, limit: int = 10):
        leads = lead_service.stale_leads(db, user, days, limit)
        return {"count": len(leads), "leads": [_lead_row(l) for l in leads]}, None

    def get_lead(lead_id: int):
        lead = lead_service.get_lead(db, user, lead_id)
        analysis = lead.ai_analysis or {}
        tasks = task_service.tasks_for(db, user, lead_id=lead.id)
        return {**_lead_row(lead), "email": lead.email, "phone": lead.phone, "source": lead.source,
                "notes": _clip(lead.notes, NOTE_LIMIT),
                "last_ai_assessment": {k: analysis.get(k) for k in ("score", "recommended_status", "summary",
                                                                   "next_actions")} if analysis else None,
                "open_tasks": [_task_row(t) for t in tasks[:5]]}, f"/leads/{lead.id}"

    def search_customers(query: str = "", limit: int = 10):
        customers = customer_service.list_customers(db, user, query or None, limit)
        return {"count": len(customers), "customers": [_customer_row(c) for c in customers]}, None

    def get_customer(customer_id: int):
        customer = customer_service.get_customer(db, user, customer_id)
        history = customer_service.list_interactions(db, user, customer.id)[:5]
        deals = opportunity_service.list_opportunities(db, user, customer_id=customer.id)
        return {**_customer_row(customer), "notes": _clip(customer.notes, NOTE_LIMIT),
                "recent_history": [{"date": i.created_at.date(), "type": i.type, "summary": _clip(i.summary, 200)}
                                   for i in history],
                "deals": [{"id": o.id, "title": o.title, "stage": o.stage, "value": o.value} for o in deals[:8]],
                "open_tasks": [_task_row(t) for t in task_service.tasks_for(db, user, customer_id=customer.id)[:5]]
                }, f"/customers/{customer.id}"

    def pipeline_summary():
        return opportunity_service.pipeline_summary(db, user), "/pipeline"

    def list_tasks(view: str = "open"):
        if view == "overdue":
            tasks = task_service.list_tasks(db, user, overdue_only=True, limit=20)
        else:
            wanted = TaskStatus.DONE.value if view == "done" else TaskStatus.OPEN.value
            tasks = task_service.list_tasks(db, user, status_filter=wanted, limit=20)
        return {"count": len(tasks), "tasks": [_task_row(t) for t in tasks]}, "/tasks"

    def search_knowledge(query: str, limit: int = 4):
        hits = knowledge_service.search(db, query, limit)
        return {"count": len(hits), "passages": [{"document": h.title, "document_id": h.document_id, "text": h.text}
                                                 for h in hits]}, "/knowledge"

    def qualify_lead(lead_id: int):
        lead = ai_service.qualify_lead(db, user, lead_id, request)
        a = lead.ai_analysis
        return {"lead_id": lead.id, "score": a["score"], "recommended_status": a["recommended_status"],
                "summary": a["summary"], "next_actions": a["next_actions"],
                "note": "Only a suggestion: the lead's status was not changed."}, f"/leads/{lead.id}"

    def draft_follow_up_email(lead_id: int | None = None, customer_id: int | None = None, goal: str = "",
                              tone: str = "friendly"):
        if bool(lead_id) == bool(customer_id):
            raise HTTPException(400, "Give exactly one of lead_id or customer_id")
        if lead_id:
            draft = ai_service.draft_email_for_lead(db, user, lead_id, goal or None, tone, request)
        else:
            draft = ai_service.draft_email_for_customer(db, user, customer_id, goal or None, tone, request)
        return {"draft_id": draft.id, "subject": draft.subject, "to": draft.to_email,
                "note": "Saved as a draft for a person to review. Nothing was sent."}, f"/emails/{draft.id}"

    def create_task(title: str, due_in_days: int | None = None, lead_id: int | None = None,
                    customer_id: int | None = None):
        due = date.today() + timedelta(days=due_in_days) if due_in_days is not None else None
        task = task_service.create_task(db, user, TaskCreate(title=title, due_date=due, lead_id=lead_id,
                                                             customer_id=customer_id), request)
        return {"task_id": task.id, "title": task.title, "due_date": task.due_date}, "/tasks"

    def _proposal(action_type: str, args: dict, reason: str):
        approval = approval_service.propose(db, user, action_type, args, reason, ctx.run_id, request)
        return {"approval_id": approval.id, "summary": approval.title, "status": "WAITING for a person to approve",
                "note": "This is NOT done yet. A person must approve it on the Approvals page."}, "/approvals"

    def request_send_email(draft_id: int, reason: str = ""):
        return _proposal("send_email", {"draft_id": draft_id}, reason)

    def request_lead_status_change(lead_id: int, new_status: str, reason: str = ""):
        return _proposal("change_lead_status", {"lead_id": lead_id, "status": new_status}, reason)

    def request_deal_stage_change(opportunity_id: int, new_stage: str, reason: str = ""):
        return _proposal("move_deal_stage", {"opportunity_id": opportunity_id, "stage": new_stage}, reason)

    # ---------- wrapper: limits, safe errors, trace ----------
    def wrap(name: str, description: str, schema: type[BaseModel], func: Callable, kind: str = ""):
        # kind: "ai" uses AI quota; "proposal" asks a person for approval; "" is a plain lookup or action
        def run(**kwargs) -> str:
            entry = {"tool": name, "args": kwargs, "ok": False, "summary": "", "link": None}
            ctx.trace.append(entry)
            if ctx.tool_calls >= settings.agent_max_tool_calls:
                entry["summary"] = "Skipped: too many tool calls in one request"
                return "Error: tool call limit reached for this request. Finish with what you have."
            if kind == "proposal" and ctx.proposals >= settings.agent_max_proposals:
                entry["summary"] = "Skipped: approval request limit reached"
                return ("Error: the limit of approval requests for one request was reached. "
                        "Tell the user which ones are still to do so they can ask again.")
            if kind == "ai" and ctx.ai_actions >= settings.agent_max_ai_actions:
                entry["summary"] = "Skipped: AI action limit reached"
                return ("Error: the limit of AI-powered actions for one request was reached. "
                        "Tell the user which ones are still to do so they can ask again.")
            ctx.tool_calls += 1
            if kind == "ai":
                ctx.ai_actions += 1
            elif kind == "proposal":
                ctx.proposals += 1
            try:
                data, link = func(**kwargs)
            except (AIBusy, AINotConfigured):
                entry["summary"] = "AI limit or setup problem: run stopped"
                raise  # stop the whole run: more calls would only fail
            except HTTPException as exc:
                entry["summary"] = str(exc.detail)
                return f"Error: {exc.detail}"
            except ValidationError as exc:
                entry["summary"] = "Invalid input"
                return f"Error: invalid input ({exc.errors()[0]['msg']})"
            payload = json.dumps(data, default=str)
            entry.update(ok=True, link=link, summary=_clip(payload, 160))
            return f"<data>\n{payload}\n</data>"

        return StructuredTool.from_function(func=run, name=name, description=description, args_schema=schema)

    return [
        wrap("search_leads", "Find the user's leads by text and/or status. Returns id, name, company, status, "
             "score, owner and days since last update.", SearchLeadsArgs, search_leads),
        wrap("find_stale_leads", "Find open leads nobody has touched for N days (leads that need attention).",
             StaleLeadsArgs, find_stale_leads),
        wrap("get_lead", "Get full details of one lead: contact info, notes, last AI assessment, open tasks.",
             LeadIdArgs, get_lead),
        wrap("search_customers", "Find customers by name, email or company.", SearchCustomersArgs, search_customers),
        wrap("get_customer", "Get one customer's details, recent history, deals and open tasks.",
             CustomerIdArgs, get_customer),
        wrap("get_pipeline_summary", "Sales pipeline totals: deals and value per stage, open value, won value and "
             "win rate.", NoArgs, pipeline_summary),
        wrap("list_tasks", "List the user's tasks: open, overdue or done.", ListTasksArgs, list_tasks),
        wrap("search_knowledge", "Search the company's own documents (pricing, product details, sales playbooks, "
             "policies). Use it for any question about what the company offers or how it works. Returns passages "
             "with the document title.", SearchKnowledgeArgs, search_knowledge),
        wrap("qualify_lead", "Ask the AI to score one lead 0-100 and suggest next steps. Saves the score on the lead. "
             "Uses AI quota, so only use it when asked or clearly useful.", LeadIdArgs, qualify_lead, "ai"),
        wrap("draft_follow_up_email", "Write a follow-up email DRAFT for one lead or one customer. The draft is "
             "saved for a person to review; nothing is sent. Uses AI quota.", DraftEmailArgs,
             draft_follow_up_email, "ai"),
        wrap("create_task", "Create a to-do task for the user, optionally linked to a lead or customer.",
             CreateTaskArgs, create_task),
        wrap("request_send_email", "ASK for approval to send an existing email draft. Nothing is sent until a "
             "person approves it. Only for drafts that exist.", RequestSendEmailArgs, request_send_email, "proposal"),
        wrap("request_lead_status_change", "ASK for approval to change a lead's status. Nothing changes until a "
             "person approves it.", RequestLeadStatusArgs, request_lead_status_change, "proposal"),
        wrap("request_deal_stage_change", "ASK for approval to move a deal to another stage. Nothing changes until "
             "a person approves it.", RequestDealStageArgs, request_deal_stage_change, "proposal"),
    ]
