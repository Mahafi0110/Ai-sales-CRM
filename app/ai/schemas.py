"""The exact shape of what we ask the AI to return. Anything else is rejected."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _clip_list(value, limit: int):
    if isinstance(value, list):
        return [str(item).strip()[:300] for item in value if str(item).strip()][:limit]
    return value


class QualificationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    recommended_status: Literal["new", "contacted", "qualified", "unqualified"]
    summary: str = Field(min_length=1, max_length=1500)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(min_length=1)

    @field_validator("strengths", "gaps", mode="before")
    @classmethod
    def _short_lists(cls, value):
        return _clip_list(value, 5)

    @field_validator("next_actions", mode="before")
    @classmethod
    def _short_actions(cls, value):
        return _clip_list(value, 5)


class EmailDraftResult(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
