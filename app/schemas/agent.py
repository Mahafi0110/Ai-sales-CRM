from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=3, max_length=1000)


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    prompt: str
    answer: str | None
    status: str
    error: str | None
    trace: list | None
    steps: int
    ai_model: str | None
    duration_ms: int | None
    created_at: datetime
