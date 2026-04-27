from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)


class UserResponse(BaseModel):
    user_id: str
    username: str
    created_at: datetime
    updated_at: datetime


class ChatCreateResponse(BaseModel):
    chat_id: str
    title: str


class ChatInfo(BaseModel):
    user_id: str
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatListResponse(BaseModel):
    items: List[ChatInfo]


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatMessageResponse(BaseModel):
    role: str
    content: str


class ChatDetailResponse(BaseModel):
    user_id: str
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageResponse]
    document_ready: bool
    document_url: Optional[str] = None
    version: Optional[int] = None


class MessageResponse(BaseModel):
    success: bool
    agent_message: str
    processing_steps: List[str] = Field(default_factory=list)
    document_ready: bool
    document_url: Optional[str] = None
    version: Optional[int] = None
    error: Optional[str] = None


class ResetResponse(BaseModel):
    success: bool
    message: str
