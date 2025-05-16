from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str | None = None
    type: Literal["text", "image", "audio"] = "text"
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

class SummaryResponse(BaseModel):
    uuid: str
    summary: str

class SearchRequest(BaseModel):
    uuid: str
    query: str
    top_k: int = 5

class SearchResponse(BaseModel):
    uuid: str
    hits: list[Message]

class FilterRequest(BaseModel):
    uuid: str
    query: str
    top_k: int = 10
    delete_irrelevant: bool = False

class FilterResponse(BaseModel):
    uuid: str
    kept: list[Message]
    removed: list[str]
    confidence: float
