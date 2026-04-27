from __future__ import annotations

import json
import logging
from pathlib import Path
from queue import Empty

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from agent.schema import MessageRole
from api.chat_store import ChatStore
from api.schemas import (
    ChatCreateResponse,
    ChatDetailResponse,
    ChatInfo,
    ChatListResponse,
    ChatMessageResponse,
    LoginRequest,
    MessageRequest,
    MessageResponse,
    ResetResponse,
    UserResponse,
)


logger = logging.getLogger(__name__)


def build_router(agent, state_manager, chat_store: ChatStore) -> APIRouter:
    router = APIRouter()

    def format_sse(event_name: str, data: dict) -> str:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event_name}\ndata: {payload}\n\n"

    def require_user(user_id: str):
        user = chat_store.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return user

    def require_chat(user_id: str, chat_id: str):
        chat = chat_store.get_chat(user_id, chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found.")
        return chat

    @router.post("/api/session/login", response_model=UserResponse)
    def login(payload: LoginRequest) -> UserResponse:
        user = chat_store.login_or_create_user(payload.username)
        logger.info("User logged in | user_id=%s | username=%s", user.user_id, user.username)
        return UserResponse(
            user_id=user.user_id,
            username=user.username,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @router.get("/api/users/{user_id}", response_model=UserResponse)
    def get_user(user_id: str) -> UserResponse:
        user = require_user(user_id)
        return UserResponse(
            user_id=user.user_id,
            username=user.username,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @router.get("/api/users/{user_id}/chats", response_model=ChatListResponse)
    def list_chats(user_id: str) -> ChatListResponse:
        require_user(user_id)
        items = [
            ChatInfo(
                user_id=chat.user_id,
                chat_id=chat.chat_id,
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
            )
            for chat in chat_store.list_chats(user_id)
        ]
        return ChatListResponse(items=items)

    @router.post("/api/users/{user_id}/chats", response_model=ChatCreateResponse)
    def create_chat(user_id: str) -> ChatCreateResponse:
        require_user(user_id)
        chat = chat_store.create_chat(user_id)
        state_manager.get_or_create(chat.chat_id)
        logger.info("Created chat %s for user %s", chat.chat_id, user_id)
        return ChatCreateResponse(chat_id=chat.chat_id, title=chat.title)

    @router.delete("/api/users/{user_id}/chats/{chat_id}")
    def delete_chat(user_id: str, chat_id: str) -> dict[str, bool]:
        require_user(user_id)
        require_chat(user_id, chat_id)
        state_manager.delete(chat_id)
        deleted = chat_store.delete_chat(user_id, chat_id)
        logger.info("Deleted chat %s for user %s", chat_id, user_id)
        return {"success": deleted}

    @router.get("/api/users/{user_id}/chats/{chat_id}", response_model=ChatDetailResponse)
    def get_chat(user_id: str, chat_id: str) -> ChatDetailResponse:
        chat = require_chat(user_id, chat_id)
        state = state_manager.get_or_create(chat_id)

        messages = [
            ChatMessageResponse(
                role=message.role.value if isinstance(message.role, MessageRole) else str(message.role),
                content=message.content,
            )
            for message in state.message_history
        ]

        document_ready = bool(state.current_pdf_path)
        document_url = f"/api/users/{user_id}/chats/{chat_id}/document" if document_ready else None

        return ChatDetailResponse(
            user_id=chat.user_id,
            chat_id=chat.chat_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            messages=messages,
            document_ready=document_ready,
            document_url=document_url,
            version=state.version if state.version > 0 else None,
        )

    @router.get("/api/users/{user_id}/chats/{chat_id}/events")
    def stream_chat_events(user_id: str, chat_id: str):
        require_chat(user_id, chat_id)
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

    @router.post("/api/users/{user_id}/chats/{chat_id}/messages", response_model=MessageResponse)
    def send_message(user_id: str, chat_id: str, payload: MessageRequest) -> MessageResponse:
        require_chat(user_id, chat_id)

        user_message = payload.message.strip()
        if not user_message:
            raise HTTPException(status_code=400, detail="Message is empty.")

        logger.info("Received message for user=%s chat=%s | text=%s", user_id, chat_id, user_message[:200])
        chat_store.update_title_if_default(user_id, chat_id, user_message)

        result = agent.handle_message(chat_id, user_message)
        chat_store.touch_chat(user_id, chat_id)

        document_url = f"/api/users/{user_id}/chats/{chat_id}/document" if result.pdf_ready else None
        return MessageResponse(
            success=result.success,
            agent_message=result.message,
            processing_steps=result.processing_steps,
            document_ready=result.pdf_ready,
            document_url=document_url,
            version=result.version,
            error=result.error,
        )

    @router.post("/api/users/{user_id}/chats/{chat_id}/reset", response_model=ResetResponse)
    def reset_chat_context(user_id: str, chat_id: str) -> ResetResponse:
        require_chat(user_id, chat_id)
        result = agent.reset_session(chat_id)
        chat_store.touch_chat(user_id, chat_id)
        logger.info("Reset chat context | user=%s | chat=%s", user_id, chat_id)
        return ResetResponse(success=result.success, message=result.message)

    @router.get("/api/users/{user_id}/chats/{chat_id}/document")
    def download_document(user_id: str, chat_id: str):
        require_chat(user_id, chat_id)
        state = state_manager.get_or_create(chat_id)
        if not state.current_pdf_path:
            raise HTTPException(status_code=404, detail="Document not found.")

        pdf_path = Path(state.current_pdf_path)
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF file is missing on disk.")

        logger.info("Downloading PDF for user=%s chat=%s | path=%s", user_id, chat_id, pdf_path)
        return FileResponse(
            path=str(pdf_path),
            filename=pdf_path.name,
            media_type="application/pdf",
        )

    return router
