from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    event_year: int = Field(default=2026, ge=2020, le=2100)
    include_alumni: bool = True
    role: str = Field(default="grantee", pattern="^(grantee|advisor)$")


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, pattern="^[0-9a-f]{32}$")
    mode: str | None = Field(default=None, pattern="^(llm|extractive|auto)$")
    event_year: int | None = Field(default=None, ge=2020, le=2100)
    include_alumni: bool = True
    role: str = Field(default="grantee", pattern="^(grantee|advisor)$")


class FeedbackIn(BaseModel):
    conversation_id: str = Field(min_length=8, max_length=64)
    turn: int = Field(ge=1)
    rating: str = Field(pattern="^(up|down)$")
    comment: str | None = Field(default=None, max_length=2000)
    question: str | None = Field(default=None, max_length=2000)


class UnansweredIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    turn: int | None = None
    reason: str = Field(default="user_flag", max_length=80)
    event_year: int | None = None
