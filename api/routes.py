from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from agent.schema import MessageRole
from api.schemas import (
    ChatCreateResponse,
    ChatDetailResponse,
    ChatInfo,
    ChatListResponse,
    ChatMessageResponse,
    MessageRequest,
    MessageResponse,
    ResetResponse,
)


logger = logging.getLogger(__name__)


@dataclass
class ChatMeta:
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatRegistry:
    def __init__(self) -> None:
        self._items: Dict[str, ChatMeta] = {}

    def create_chat(self) -> ChatMeta:
        now = datetime.utcnow()
        chat_id = str(uuid.uuid4())
        chat = ChatMeta(
            chat_id=chat_id,
            title="Новый чат",
            created_at=now,
            updated_at=now,
        )
        self._items[chat_id] = chat
        return chat

    def list_chats(self) -> list[ChatMeta]:
        return sorted(
            self._items.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def get_chat(self, chat_id: str) -> ChatMeta | None:
        return self._items.get(chat_id)

    def touch_chat(self, chat_id: str) -> None:
        chat = self._items.get(chat_id)
        if chat:
            chat.updated_at = datetime.utcnow()

    def update_title_if_default(self, chat_id: str, user_message: str) -> None:
        chat = self._items.get(chat_id)
        if not chat:
            return

        if chat.title == "Новый чат":
            cleaned = " ".join(user_message.strip().split())
            if cleaned:
                chat.title = cleaned[:60]
            chat.updated_at = datetime.utcnow()


def build_router(agent, state_manager, chat_registry: ChatRegistry) -> APIRouter:
    router = APIRouter()

    def format_sse(event_name: str, data: dict) -> str:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event_name}\ndata: {payload}\n\n"

    @router.get("/api/chats", response_model=ChatListResponse)
    def list_chats() -> ChatListResponse:
        items = [
            ChatInfo(
                chat_id=chat.chat_id,
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )
            for chat in chat_registry.list_chats()
        ]
        return ChatListResponse(items=items)

    @router.post("/api/chats", response_model=ChatCreateResponse)
    def create_chat() -> ChatCreateResponse:
        chat = chat_registry.create_chat()
        state_manager.get_or_create(chat.chat_id)
        logger.info("Created chat %s", chat.chat_id)

        return ChatCreateResponse(
            chat_id=chat.chat_id,
            title=chat.title,
        )

    @router.get("/api/chats/{chat_id}", response_model=ChatDetailResponse)
    def get_chat(chat_id: str) -> ChatDetailResponse:
        chat = chat_registry.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")

        state = state_manager.get_or_create(chat_id)

        messages = [
            ChatMessageResponse(
                role=message.role.value if isinstance(message.role, MessageRole) else str(message.role),
                content=message.content,
            )
            for message in state.message_history
        ]

        document_ready = bool(state.current_pdf_path)
        document_url = f"/api/chats/{chat_id}/document" if document_ready else None
        logger.info(
            "Fetched chat %s | messages=%s | document_ready=%s | version=%s",
            chat_id,
            len(messages),
            document_ready,
            state.version if state.version > 0 else None,
        )

        return ChatDetailResponse(
            chat_id=chat.chat_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            messages=messages,
            document_ready=document_ready,
            document_url=document_url,
            version=state.version if state.version > 0 else None,
        )

    @router.get("/api/chats/{chat_id}/events")
    def stream_chat_events(chat_id: str):
        chat = chat_registry.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")

        subscriber = state_manager.subscribe(chat_id)

        def event_stream():
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        event = subscriber.get(timeout=15)
                    except Empty:
                        yield ": keep-alive\n\n"
                        continue

                    yield format_sse(event["event"], event["data"])
            finally:
                state_manager.unsubscribe(chat_id, subscriber)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/api/chats/{chat_id}/messages", response_model=MessageResponse)
    def send_message(chat_id: str, payload: MessageRequest) -> MessageResponse:
        chat = chat_registry.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")

        user_message = payload.message.strip()
        if not user_message:
            raise HTTPException(status_code=400, detail="Message is empty.")

        logger.info("Received message for chat %s | text=%s", chat_id, user_message[:200])

        chat_registry.update_title_if_default(chat_id, user_message)

        result = agent.handle_message(chat_id, user_message)
        chat_registry.touch_chat(chat_id)

        document_url = f"/api/chats/{chat_id}/document" if result.pdf_ready else None
        logger.info(
            "Handled message for chat %s | success=%s | pdf_ready=%s | version=%s | error=%s",
            chat_id,
            result.success,
            result.pdf_ready,
            result.version,
            result.error,
        )

        return MessageResponse(
            success=result.success,
            agent_message=result.message,
            processing_steps=result.processing_steps,
            document_ready=result.pdf_ready,
            document_url=document_url,
            version=result.version,
            error=result.error,
        )

    @router.post("/api/chats/{chat_id}/reset", response_model=ResetResponse)
    def reset_chat_context(chat_id: str) -> ResetResponse:
        chat = chat_registry.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")

        result = agent.reset_session(chat_id)
        chat_registry.touch_chat(chat_id)
        logger.info("Reset chat context for %s", chat_id)

        return ResetResponse(
            success=result.success,
            message=result.message,
        )

    @router.get("/api/chats/{chat_id}/document")
    def download_document(chat_id: str):
        chat = chat_registry.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")

        state = state_manager.get_or_create(chat_id)
        if not state.current_pdf_path:
            raise HTTPException(status_code=404, detail="Document not found.")

        pdf_path = Path(state.current_pdf_path)
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF file is missing on disk.")

        logger.info("Downloading PDF for chat %s | path=%s", chat_id, pdf_path)

        return FileResponse(
            path=str(pdf_path),
            filename=pdf_path.name,
            media_type="application/pdf",
        )

    return router
