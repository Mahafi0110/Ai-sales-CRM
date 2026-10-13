"""HTML pages for the CRM: leads, customers, pipeline and tasks (server-rendered with Jinja2)."""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import page_user
from app.models.crm import LeadStatus, Stage, TaskStatus
from app.models.user import User
from app.routers.pages import render
from app.schemas.crm import (CustomerCreate, CustomerUpdate, InteractionCreate, LeadCreate, LeadUpdate,
                             OpportunityCreate, TaskCreate)
from app.services import (access, customer_service, lead_service, opportunity_service, task_service)

router = APIRouter(include_in_schema=False)

LEAD_STATUSES = [s.value for s in LeadStatus]
SETTABLE_LEAD_STATUSES = [s.value for s in LeadStatus if s != LeadStatus.CONVERTED]
STAGES = [s.value for s in Stage]


# ---------- small helpers ----------
def blank(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def to_int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        field = str(first["loc"][-1]).replace("_", " ") if first["loc"] else "form"
        return f"Please check '{field}': {first['msg']}"
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return "Something went wrong"


def back(url: str, msg: str | None = None, error: str | None = None) -> RedirectResponse:
    query = urlencode({k: v for k, v in (("msg", msg), ("error", error)) if v})
    if query:
        url += ("&" if "?" in url else "?") + query
    return RedirectResponse(url, status_code=303)


def safe_next(next_url: str | None, default: str) -> str:
    """Only allow redirects to pages inside this site."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return default


def team_users(db: Session, user: User) -> list[User]:
    """The people a manager can assign work to (empty for sales reps)."""
    if not access.is_manager(user):
        return []
    return list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)))


# ---------- leads ----------
@router.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, q: str = "", status_filter: str = Query("", alias="status"), owner: str = "",
               user: User = Depends(page_user), db: Session = Depends(get_db)):
    leads = lead_service.list_leads(db, user, blank(q), blank(status_filter), to_int(owner))
    return render(request, "leads.html", user, active="leads", leads=leads, q=q, status_filter=status_filter,
                  owner=owner, statuses=LEAD_STATUSES, team=team_users(db, user))


@router.post("/leads")
def leads_create(request: Request, name: str = Form(""), email: str = Form(""), phone: str = Form(""),
                 company: str = Form(""), source: str = Form(""), notes: str = Form(""), owner_id: str = Form(""),
                 user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = LeadCreate(name=name.strip(), email=blank(email), phone=blank(phone), company=blank(company),
                          source=blank(source), notes=blank(notes), owner_id=to_int(owner_id))
        lead = lead_service.create_lead(db, user, data, request)
    except (ValidationError, HTTPException) as exc:
        return back("/leads", error=error_text(exc))
    return back(f"/leads/{lead.id}", msg="Lead created")


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(lead_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    lead = lead_service.get_lead(db, user, lead_id)
    return render(request, "lead_detail.html", user, active="leads", lead=lead, statuses=SETTABLE_LEAD_STATUSES,
                  team=team_users(db, user), tasks=task_service.tasks_for(db, user, lead_id=lead.id))


@router.post("/leads/{lead_id}/edit")
def lead_edit(lead_id: int, request: Request, name: str = Form(""), email: str = Form(""), phone: str = Form(""),
              company: str = Form(""), source: str = Form(""), notes: str = Form(""),
              user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = LeadUpdate(name=name.strip(), email=blank(email), phone=blank(phone), company=blank(company),
                          source=blank(source), notes=blank(notes))
        lead_service.update_lead(db, user, lead_id, data, request)
    except (ValidationError, HTTPException) as exc:
        return back(f"/leads/{lead_id}", error=error_text(exc))
    return back(f"/leads/{lead_id}", msg="Lead saved")


@router.post("/leads/{lead_id}/status")
def lead_status(lead_id: int, request: Request, status: str = Form(...),
                user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        lead_service.set_status(db, user, lead_id, LeadStatus(status), request)
    except (ValueError, HTTPException) as exc:
        return back(f"/leads/{lead_id}", error=error_text(exc) if isinstance(exc, HTTPException) else "Unknown status")
    return back(f"/leads/{lead_id}", msg="Status updated")


@router.post("/leads/{lead_id}/assign")
def lead_assign(lead_id: int, request: Request, owner_id: str = Form(""),
                user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        lead_service.assign_lead(db, user, lead_id, to_int(owner_id) or 0, request)
    except HTTPException as exc:
        return back(f"/leads/{lead_id}", error=error_text(exc))
    return back(f"/leads/{lead_id}", msg="Lead assigned")


@router.post("/leads/{lead_id}/convert")
def lead_convert(lead_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        customer = lead_service.convert_to_customer(db, user, lead_id, request)
    except HTTPException as exc:
        return back(f"/leads/{lead_id}", error=error_text(exc))
    return back(f"/customers/{customer.id}", msg="Lead converted to a customer")


# ---------- customers ----------
@router.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, q: str = "", user: User = Depends(page_user), db: Session = Depends(get_db)):
    return render(request, "customers.html", user, active="customers", q=q,
                  customers=customer_service.list_customers(db, user, blank(q)), team=team_users(db, user))


@router.post("/customers")
def customers_create(request: Request, name: str = Form(""), email: str = Form(""), phone: str = Form(""),
                     company: str = Form(""), industry: str = Form(""), notes: str = Form(""),
                     owner_id: str = Form(""), user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = CustomerCreate(name=name.strip(), email=blank(email), phone=blank(phone), company=blank(company),
                              industry=blank(industry), notes=blank(notes), owner_id=to_int(owner_id))
        customer = customer_service.create_customer(db, user, data, request)
    except (ValidationError, HTTPException) as exc:
        return back("/customers", error=error_text(exc))
    return back(f"/customers/{customer.id}", msg="Customer created")


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(customer_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    customer = customer_service.get_customer(db, user, customer_id)
    return render(request, "customer_detail.html", user, active="customers", customer=customer,
                  interactions=customer_service.list_interactions(db, user, customer.id),
                  opportunities=opportunity_service.list_opportunities(db, user, customer_id=customer.id),
                  tasks=task_service.tasks_for(db, user, customer_id=customer.id), stages=STAGES)


@router.post("/customers/{customer_id}/edit")
def customer_edit(customer_id: int, request: Request, name: str = Form(""), email: str = Form(""),
                  phone: str = Form(""), company: str = Form(""), industry: str = Form(""), notes: str = Form(""),
                  user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = CustomerUpdate(name=name.strip(), email=blank(email), phone=blank(phone), company=blank(company),
                              industry=blank(industry), notes=blank(notes))
        customer_service.update_customer(db, user, customer_id, data, request)
    except (ValidationError, HTTPException) as exc:
        return back(f"/customers/{customer_id}", error=error_text(exc))
    return back(f"/customers/{customer_id}", msg="Customer saved")


@router.post("/customers/{customer_id}/interactions")
def customer_add_interaction(customer_id: int, request: Request, type: str = Form("note"), summary: str = Form(""),
                             user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = InteractionCreate(type=type, summary=summary.strip())
        customer_service.add_interaction(db, user, customer_id, data, request)
    except (ValidationError, HTTPException) as exc:
        return back(f"/customers/{customer_id}", error=error_text(exc))
    return back(f"/customers/{customer_id}", msg="Interaction added")


# ---------- pipeline ----------
@router.get("/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    opps = opportunity_service.list_opportunities(db, user)
    columns = [{"stage": s, "items": [o for o in opps if o.stage == s]} for s in STAGES]
    return render(request, "pipeline.html", user, active="pipeline", columns=columns, stages=STAGES,
                  summary=opportunity_service.pipeline_summary(db, user),
                  customers=customer_service.list_customers(db, user, limit=500), team=team_users(db, user))


@router.post("/pipeline")
def pipeline_create(request: Request, title: str = Form(""), customer_id: str = Form(""), value: str = Form("0"),
                    expected_close_date: str = Form(""), stage: str = Form("prospecting"), owner_id: str = Form(""),
                    user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        data = OpportunityCreate(title=title.strip(), customer_id=to_int(customer_id) or 0,
                                 value=blank(value) or "0", expected_close_date=blank(expected_close_date),
                                 stage=stage, owner_id=to_int(owner_id))
        opportunity_service.create_opportunity(db, user, data, request)
    except (ValidationError, HTTPException) as exc:
        return back("/pipeline", error=error_text(exc))
    return back("/pipeline", msg="Opportunity added")


@router.post("/opportunities/{opp_id}/stage")
def opportunity_stage(opp_id: int, request: Request, stage: str = Form(...), next: str = Form("/pipeline"),
                      user: User = Depends(page_user), db: Session = Depends(get_db)):
    target = safe_next(next, "/pipeline")
    try:
        opportunity_service.move_stage(db, user, opp_id, Stage(stage), request)
    except (ValueError, HTTPException) as exc:
        return back(target, error=error_text(exc) if isinstance(exc, HTTPException) else "Unknown stage")
    return back(target, msg="Stage updated")


# ---------- tasks ----------
@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, view: str = "open", user: User = Depends(page_user), db: Session = Depends(get_db)):
    if view == "overdue":
        tasks = task_service.list_tasks(db, user, overdue_only=True)
    elif view == "done":
        tasks = task_service.list_tasks(db, user, status_filter=TaskStatus.DONE.value)
    else:
        view = "open"
        tasks = task_service.list_tasks(db, user, status_filter=TaskStatus.OPEN.value)
    return render(request, "tasks.html", user, active="tasks", tasks=tasks, view=view, team=team_users(db, user))


@router.post("/tasks")
def tasks_create(request: Request, title: str = Form(""), description: str = Form(""), due_date: str = Form(""),
                 assigned_to_id: str = Form(""), lead_id: str = Form(""), customer_id: str = Form(""),
                 opportunity_id: str = Form(""), next: str = Form("/tasks"),
                 user: User = Depends(page_user), db: Session = Depends(get_db)):
    target = safe_next(next, "/tasks")
    try:
        data = TaskCreate(title=title.strip(), description=blank(description), due_date=blank(due_date),
                          assigned_to_id=to_int(assigned_to_id), lead_id=to_int(lead_id),
                          customer_id=to_int(customer_id), opportunity_id=to_int(opportunity_id))
        task_service.create_task(db, user, data, request)
    except (ValidationError, HTTPException) as exc:
        return back(target, error=error_text(exc))
    return back(target, msg="Task added")


@router.post("/tasks/{task_id}/toggle")
def tasks_toggle(task_id: int, request: Request, next: str = Form("/tasks"),
                 user: User = Depends(page_user), db: Session = Depends(get_db)):
    target = safe_next(next, "/tasks")
    try:
        task = task_service.get_task(db, user, task_id)
        task_service.set_done(db, user, task_id, task.status == TaskStatus.OPEN.value, request)
    except HTTPException as exc:
        return back(target, error=error_text(exc))
    return back(target)
