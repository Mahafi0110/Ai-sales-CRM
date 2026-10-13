from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.crm import InteractionType, LeadStatus, Stage


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Leads ----------
class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=60)
    notes: str | None = None
    owner_id: int | None = None


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=60)
    notes: str | None = None


class LeadStatusUpdate(BaseModel):
    status: LeadStatus


class AssignRequest(BaseModel):
    owner_id: int


class LeadOut(_Out):
    id: int
    name: str
    email: str | None
    phone: str | None
    company: str | None
    source: str | None
    status: str
    score: int | None
    ai_analysis: dict | None
    notes: str | None
    owner_id: int | None
    customer_id: int | None
    created_at: datetime


# ---------- Customers ----------
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    industry: str | None = Field(default=None, max_length=80)
    notes: str | None = None
    owner_id: int | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=160)
    industry: str | None = Field(default=None, max_length=80)
    notes: str | None = None


class CustomerOut(_Out):
    id: int
    name: str
    email: str | None
    phone: str | None
    company: str | None
    industry: str | None
    notes: str | None
    owner_id: int | None
    created_at: datetime


class InteractionCreate(BaseModel):
    type: InteractionType = InteractionType.NOTE
    summary: str = Field(min_length=1)


class InteractionOut(_Out):
    id: int
    customer_id: int
    type: str
    summary: str
    created_by_id: int | None
    created_at: datetime


# ---------- Opportunities ----------
class OpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    customer_id: int
    value: Decimal = Field(default=Decimal("0"), ge=0)
    expected_close_date: date | None = None
    stage: Stage = Stage.PROSPECTING
    owner_id: int | None = None


class OpportunityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    value: Decimal | None = Field(default=None, ge=0)
    expected_close_date: date | None = None


class StageUpdate(BaseModel):
    stage: Stage


class OpportunityOut(_Out):
    id: int
    title: str
    customer_id: int
    owner_id: int | None
    stage: str
    value: Decimal
    expected_close_date: date | None
    closed_at: datetime | None
    created_at: datetime


# ---------- Tasks ----------
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    due_date: date | None = None
    assigned_to_id: int | None = None
    lead_id: int | None = None
    customer_id: int | None = None
    opportunity_id: int | None = None


class TaskOut(_Out):
    id: int
    title: str
    description: str | None
    due_date: date | None
    status: str
    assigned_to_id: int | None
    lead_id: int | None
    customer_id: int | None
    opportunity_id: int | None
    created_at: datetime


# ---------- Dashboard ----------
class PipelineStageOut(BaseModel):
    stage: str
    count: int
    value: Decimal


class PipelineSummaryOut(BaseModel):
    stages: list[PipelineStageOut]
    open_count: int
    open_value: Decimal
    won_value: Decimal
    win_rate: float | None


class DashboardOut(BaseModel):
    open_leads: int
    leads_by_status: dict[str, int]
    customers: int
    open_opportunities: int
    pipeline_value: Decimal
    won_value: Decimal
    win_rate: float | None
    open_tasks: int
    overdue_tasks: int
    pending_approvals: int = 0
    recent_leads: list[LeadOut]
    upcoming_tasks: list[TaskOut]
