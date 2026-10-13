"""Login, logout, dashboard and the shared Jinja2 setup used by all HTML pages."""
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import COOKIE_NAME, get_current_user_or_none, page_user
from app.models.user import User
from app.routers.auth import set_login_cookie
from app.services import audit_service, dashboard_service, opportunity_service, user_service

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _money(value) -> str:
    return f"{get_settings().currency_symbol}{float(value or 0):,.0f}"


def _date(value) -> str:
    return value.strftime("%d %b %Y") if value else "-"


templates.env.filters["money"] = _money
templates.env.filters["date"] = _date
templates.env.globals["today"] = date.today


def render(request: Request, name: str, user: User | None = None, status_code: int = 200, **ctx):
    ctx.update(user=user, app_name=get_settings().app_name, ai_ready=llm.is_configured())
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


@router.get("/", response_class=HTMLResponse)
def home(user: User | None = Depends(get_current_user_or_none)):
    return RedirectResponse("/dashboard" if user else "/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(get_current_user_or_none)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = user_service.authenticate(db, email, password)
    if not user:
        audit_service.log_action(db, "login_failed", details={"email": email}, request=request)
        return render(request, "login.html", status_code=401, error="Incorrect email or password", email=email)
    response = RedirectResponse("/dashboard", status_code=303)
    set_login_cookie(response, user.id)
    audit_service.log_action(db, "login", user_id=user.id, request=request)
    return response


@router.post("/logout")
def logout_submit(request: Request, user: User | None = Depends(get_current_user_or_none), db: Session = Depends(get_db)):
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    if user:
        audit_service.log_action(db, "logout", user_id=user.id, request=request)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    return render(request, "dashboard.html", user=user, active="dashboard",
                  stats=dashboard_service.get_stats(db, user),
                  pipeline=opportunity_service.pipeline_summary(db, user))
