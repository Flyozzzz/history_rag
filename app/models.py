from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str | None = None
    type: Literal["text", "image", "audio", "video", "document"] = "text"
    extra: Optional[Dict[str, Any]] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
    importance: int = Field(0, ge=0, le=10)
    tags: Optional[List[str]] = None


class HistoryResponse(BaseModel):
    messages: list[Message]
    relevant: list[Message] | None = None
    facts: Message | None = None
    summary: str | None = None


class AddRequest(BaseModel):
    uuid: str
    messages: list[Message]
    chat_id: str | None = None


class SummaryResponse(BaseModel):
    uuid: str
    summary: str


class SearchRequest(BaseModel):
    uuid: str
    query: str
    top_k: int = 5
    tags: list[str] | None = None
    chat_id: str | None = None


class SearchResponse(BaseModel):
    uuid: str
    hits: list[Message]


class FilterRequest(BaseModel):
    uuid: str
    query: str
    top_k: int = 10
    delete_irrelevant: bool = False
    chat_id: str | None = None


class FilterResponse(BaseModel):
    uuid: str
    kept: list[Message]
    removed: list[str]
    confidence: float


class RegisterRequest(BaseModel):
    username: str
    password: str
    company_id: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    uuid: str
    token: str


class CompanyRegisterRequest(BaseModel):
    name: str
    password: str
    idle_timeout: int = Field(0, ge=0)
    enable_summary: bool = True
    enable_facts: bool = True
    enable_calendar: bool = True


class CompanyLoginRequest(BaseModel):
    name: str
    password: str


class CompanyAuthResponse(BaseModel):
    name: str
    token: str


class CompanyFlagsUpdate(BaseModel):
    enable_summary: bool | None = None
    enable_facts: bool | None = None
    enable_calendar: bool | None = None


class CompanyFlagsResponse(BaseModel):
    enable_summary: bool
    enable_facts: bool
    enable_calendar: bool


class CalendarEvent(BaseModel):
    when: datetime
    text: str
    chat_id: str | None = None
    tz: str | None = None


class CalendarResponse(BaseModel):
    uuid: str
    events: list[CalendarEvent]


class CalendarUpdateRequest(BaseModel):
    uuid: str
    when: datetime | None = None
    text: str | None = None


class CalendarDeleteRequest(BaseModel):
    uuid: str


class CalendarChatRequest(BaseModel):
    uuid: str
    query: str
    tz: str | None = "UTC"


class FactsResponse(BaseModel):
    uuid: str
    facts: list[str]


class DeleteFactRequest(BaseModel):
    uuid: str
    fact: str


class DeleteFactResponse(BaseModel):
    uuid: str
    removed: int
