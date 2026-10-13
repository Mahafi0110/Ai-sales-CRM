"""The AI Assistant pages."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.agent import service
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import page_user
from app.models.user import User
from app.routers.crm_pages import back, error_text
from app.routers.pages import render
from app.services import approval_service

router = APIRouter(include_in_schema=False)

SUGGESTIONS = [
    "Which of my open leads have gone quiet for a week? Tell me what to do about the top three.",
    "Summarize my pipeline and tell me what needs attention.",
    "Qualify my newest lead and write a follow-up email for it.",
    "What tasks are overdue? Create a task to review them tomorrow.",
]


@router.get("/assistant", response_class=HTMLResponse)
def assistant_page(request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    limit = get_settings().agent_runs_per_hour
    return render(request, "assistant.html", user, active="assistant", suggestions=SUGGESTIONS,
                  runs=service.list_runs(db, user, 10), remaining=max(limit - service.runs_last_hour(db, user), 0))


@router.post("/assistant")
def assistant_run(request: Request, message: str = Form(""), user: User = Depends(page_user),
                  db: Session = Depends(get_db)):
    message = message.strip()
    if len(message) < 3:
        return back("/assistant", error="Please type what you would like help with.")
    if len(message) > 1000:
        return back("/assistant", error="Please keep the request under 1000 characters.")
    try:
        run = service.run_agent(db, user, message, request)
    except HTTPException as exc:
        return back("/assistant", error=error_text(exc))
    return back(f"/assistant/{run.id}")


@router.get("/assistant/{run_id}", response_class=HTMLResponse)
def assistant_result(run_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    run = service.get_run(db, user, run_id)
    return render(request, "assistant_run.html", user, active="assistant", run=run,
                  approvals=approval_service.for_run(db, user, run.id))
