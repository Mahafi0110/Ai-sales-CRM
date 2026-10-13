from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import page_user
from app.models.user import User
from app.routers.crm_pages import back, error_text
from app.routers.pages import render
from app.services import approval_service

router = APIRouter(include_in_schema=False)


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request, tab: str = "waiting", user: User = Depends(page_user),
                   db: Session = Depends(get_db)):
    tab = "history" if tab == "history" else "waiting"
    return render(request, "approvals.html", user, active="approvals", tab=tab,
                  approvals=approval_service.list_approvals(db, user, tab),
                  labels={k: v.label for k, v in approval_service.ACTIONS.items()})


@router.post("/approvals/{approval_id}/approve")
def approval_approve(approval_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        approval = approval_service.approve(db, user, approval_id, request)
    except HTTPException as exc:
        return back("/approvals", error=error_text(exc))
    if approval.status == "executed":
        return back("/approvals", msg="Approved and done.")
    return back("/approvals", error=f"Approved, but it could not be completed: {approval.error}")


@router.post("/approvals/{approval_id}/reject")
def approval_reject(approval_id: int, request: Request, note: str = Form(""), user: User = Depends(page_user),
                    db: Session = Depends(get_db)):
    try:
        approval_service.reject(db, user, approval_id, note, request)
    except HTTPException as exc:
        return back("/approvals", error=error_text(exc))
    return back("/approvals", msg="Rejected. Nothing was changed.")
