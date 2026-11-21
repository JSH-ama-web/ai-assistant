"""Pydantic 모델 — 요청 검증과 응답 형태를 한곳에서 정의한다."""
from __future__ import annotations

import math
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── 데이터 ────────────────────────────────────────────
class DataBase(BaseModel):
    date: Date = Field(..., description="YYYY-MM-DD", examples=["2026-11-20"])
    value: float = Field(..., ge=0, le=1_000_000, description="측정값 (예: 운동 시간, 분)", examples=[75])
    memo: str = Field("", max_length=200, description="메모 (예: 복싱)", examples=["복싱"])

    @field_validator("value")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value 는 유한한 숫자여야 합니다.")
        return round(v, 4)

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, v: str) -> str:
        return v.strip()


class DataCreate(DataBase):
    pass


class DataUpdate(BaseModel):
    """부분 수정 허용: 보낸 필드만 바뀐다."""
    date: Date | None = None
    value: float | None = Field(None, ge=0, le=1_000_000)
    memo: str | None = Field(None, max_length=200)

    @field_validator("value")
    @classmethod
    def finite(cls, v):
        if v is not None and not math.isfinite(v):
            raise ValueError("value 는 유한한 숫자여야 합니다.")
        return v


class DataItem(BaseModel):
    id: str
    date: str
    value: float
    memo: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class Metrics(BaseModel):
    total: float
    average: float
    max: float
    min: float
    max_date: str | None = None
    min_date: str | None = None


class Summary(BaseModel):
    period: str
    count: int
    metrics: Metrics | None
    trend: str
    recent_average: float | None = None
    previous_average: float | None = None
    unit: str = ""


class MonthlyStat(BaseModel):
    month: str
    count: int
    total: float
    average: float


class Statistics(BaseModel):
    count: int
    median: float | None
    std: float | None
    active_ratio: float | None = Field(None, description="값이 0보다 큰 날의 비율")
    longest_streak: int = Field(0, description="값>0 연속 일수 최대")
    weekday_average: dict[str, float]
    monthly: list[MonthlyStat]
    moving_average_7: list[dict]
    top_memos: list[dict]


# ── 대화 ──────────────────────────────────────────────
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
    created_at: str | None = None
    tool_calls: list[dict] | None = Field(None, description="assistant 메시지가 호출한 도구 기록")


class ConversationCreate(BaseModel):
    title: str | None = Field(None, max_length=100)
    messages: list[Message] = Field(..., min_length=1, max_length=200)


class ConversationListItem(BaseModel):
    """목록 응답에는 messages 를 포함하지 않는다 (가벼운 목록 + 상세는 GET /{id})."""
    id: str
    title: str
    message_count: int
    preview: str
    created_at: str | None = None
    updated_at: str | None = None


class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[Message]
    created_at: str | None = None
    updated_at: str | None = None


# ── 채팅 ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, examples=["이번 달 운동량 어때?"])
    conversation_id: str | None = Field(None, description="이어서 대화할 때 지정. 없으면 새 대화 생성")
    use_tools: bool = Field(True, description="Function Calling(도구 호출) 사용 여부")

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("빈 메시지는 보낼 수 없습니다.")
        return v.strip()


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    reason: str = ""


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    summary: Summary
    tool_calls: list[ToolCallLog] = []
