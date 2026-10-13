from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import models  # noqa: F401  (makes sure all tables are registered)
from app.core.config import get_settings
from app.core.deps import LoginRequired
from app.routers import (agent, agent_pages, ai, ai_pages, approval_pages, approvals, auth, crm_pages, customers,
                         health, knowledge, knowledge_pages, leads, opportunities, pages, tasks, users)

BASE_DIR = Path(__file__).resolve().parent

# Database tables are created and updated by Alembic migrations (see README): `alembic upgrade head`.
app = FastAPI(title=get_settings().app_name)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(leads.router)
app.include_router(customers.router)
app.include_router(opportunities.router)
app.include_router(tasks.router)
app.include_router(pages.router)
app.include_router(ai.router)
app.include_router(approvals.router)
app.include_router(knowledge.router)
app.include_router(agent.router)
app.include_router(crm_pages.router)
app.include_router(ai_pages.router)
app.include_router(agent_pages.router)
app.include_router(approval_pages.router)
app.include_router(knowledge_pages.router)


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """JSON errors for the API; a friendly page for people browsing the site."""
    if request.url.path.startswith(("/api", "/health", "/static")):
        return await http_exception_handler(request, exc)
    return pages.render(request, "error.html", None, status_code=exc.status_code,
                        code=exc.status_code, message=exc.detail)
