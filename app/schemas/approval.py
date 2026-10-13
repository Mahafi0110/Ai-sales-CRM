from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requested_by_id: int
    run_id: int | None
    action_type: str
    title: str
    reason: str | None
    payload: dict
    status: str
    decided_by_id: int | None
    decided_at: datetime | None
    decision_note: str | None
    result: dict | None
    error: str | None
    created_at: datetime
    executed_at: datetime | None


class ApprovalReject(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class PendingCountOut(BaseModel):
    pending: int
