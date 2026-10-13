from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AIStatusOut(BaseModel):
    configured: bool
    provider: str
    model: str


class DraftRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=500)
    tone: str = "friendly"


class EmailDraftUpdate(BaseModel):
    to_email: EmailStr | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)


class EmailDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int | None
    customer_id: int | None
    to_email: str | None
    subject: str
    body: str
    goal: str | None
    status: str
    ai_model: str | None
    sent_at: datetime | None
    sent_via: str | None
    created_by_id: int | None
    created_at: datetime
