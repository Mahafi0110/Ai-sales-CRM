from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.approval import ApprovalOut, ApprovalReject, PendingCountOut
from app.services import approval_service

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
def list_approvals(group: str = "waiting", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return approval_service.list_approvals(db, user, "history" if group == "history" else "waiting")


@router.get("/count", response_model=PendingCountOut)
def count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"pending": approval_service.count_pending(db, user)}


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return approval_service.get_approval(db, user, approval_id)


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve(approval_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Approve and run it now. The answer shows whether it worked: status 'executed' or 'failed' (with the reason)."""
    return approval_service.approve(db, user, approval_id, request)


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
def reject(approval_id: int, request: Request, data: ApprovalReject | None = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    return approval_service.reject(db, user, approval_id, data.note if data else None, request)
