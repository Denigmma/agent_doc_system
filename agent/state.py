from __future__ import annotations

import json
from queue import Queue
from threading import Lock
from pathlib import Path
from typing import Dict, Optional

from .schema import ChatMessage, MessageRole, RetrievalResult, SessionState, SessionStatus


class SessionStateManager:
    def __init__(self, storage_dir: str | Path = "storage/sessions") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, SessionState] = {}
        self._subscribers: Dict[str, list[Queue]] = {}
        self._subscribers_lock = Lock()

    def get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            loaded = self._load_state(session_id)
            self._sessions[session_id] = loaded or SessionState(session_id=session_id)
        return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state
        self._persist_state(state)

    def reset(self, session_id: str) -> SessionState:
        state = SessionState(session_id=session_id)
        self._sessions[session_id] = state
        self._persist_state(state)
        self.publish_event(session_id, "reset", {"message": "Контекст сессии сброшен."})
        return state

    def append_user_message(self, session_id: str, content: str) -> SessionState:
        state = self.get_or_create(session_id)
        state.message_history.append(ChatMessage(role=MessageRole.USER, content=content))
        self.save(state)
        return state

    def append_agent_message(self, session_id: str, content: str) -> SessionState:
        state = self.get_or_create(session_id)
        state.message_history.append(ChatMessage(role=MessageRole.AGENT, content=content))
        self.save(state)
        self.publish_event(session_id, "agent", {"content": content})
        return state

    def append_processing_message(self, session_id: str, content: str) -> SessionState:
        state = self.get_or_create(session_id)
        state.message_history.append(ChatMessage(role=MessageRole.PROCESSING, content=content))
        self.save(state)
        self.publish_event(session_id, "processing", {"content": content})
        return state

    def upsert_processing_message(self, session_id: str, content: str) -> SessionState:
        state = self.get_or_create(session_id)
        if state.message_history and state.message_history[-1].role == MessageRole.PROCESSING:
            state.message_history[-1].content = content
        else:
            state.message_history.append(ChatMessage(role=MessageRole.PROCESSING, content=content))
        self.save(state)
        self.publish_event(session_id, "processing", {"content": content})
        return state

    def mark_error(self, session_id: str, error_message: str) -> SessionState:
        state = self.get_or_create(session_id)
        state.status = SessionStatus.ERROR
        state.last_error = error_message
        self.save(state)
        self.publish_event(session_id, "error", {"error": error_message})
        return state

    def subscribe(self, session_id: str) -> Queue:
        subscriber: Queue = Queue()
        with self._subscribers_lock:
            self._subscribers.setdefault(session_id, []).append(subscriber)
        return subscriber

    def unsubscribe(self, session_id: str, subscriber: Queue) -> None:
        with self._subscribers_lock:
            subscribers = self._subscribers.get(session_id, [])
            if subscriber in subscribers:
                subscribers.remove(subscriber)
            if not subscribers and session_id in self._subscribers:
                self._subscribers.pop(session_id, None)

    def publish_event(self, session_id: str, event_type: str, data: dict) -> None:
        with self._subscribers_lock:
            subscribers = list(self._subscribers.get(session_id, []))

        event = {
            "event": event_type,
            "data": data,
        }
        for subscriber in subscribers:
            subscriber.put(event)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        state_path = self._state_path(session_id)
        if state_path.exists():
            state_path.unlink()

    def _state_path(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    def _persist_state(self, state: SessionState) -> None:
        payload = {
            "session_id": state.session_id,
            "status": state.status.value,
            "original_user_request": state.original_user_request,
            "current_template_id": state.current_template_id,
            "current_template_name": state.current_template_name,
            "current_template_description": state.current_template_description,
            "current_template_latex": state.current_template_latex,
            "current_latex": state.current_latex,
            "current_tex_path": state.current_tex_path,
            "current_pdf_path": state.current_pdf_path,
            "retrieval_results": [
                {
                    "source": item.source,
                    "query": item.query,
                    "content": item.content,
                }
                for item in state.retrieval_results
            ],
            "message_history": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in state.message_history
            ],
            "version": state.version,
            "last_error": state.last_error,
        }
        self._state_path(state.session_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_state(self, session_id: str) -> Optional[SessionState]:
        state_path = self._state_path(session_id)
        if not state_path.exists():
            return None

        raw = json.loads(state_path.read_text(encoding="utf-8"))
        status = str(raw.get("status") or SessionStatus.EMPTY.value)
        message_history = []
        for item in raw.get("message_history", []):
            try:
                role = MessageRole(str(item.get("role")))
            except Exception:
                role = MessageRole.SYSTEM
            message_history.append(
                ChatMessage(
                    role=role,
                    content=str(item.get("content") or ""),
                )
            )

        retrieval_results = [
            RetrievalResult(
                source=str(item.get("source") or ""),
                query=str(item.get("query") or ""),
                content=str(item.get("content") or ""),
            )
            for item in raw.get("retrieval_results", [])
            if isinstance(item, dict)
        ]

        return SessionState(
            session_id=session_id,
            status=SessionStatus(status) if status in {item.value for item in SessionStatus} else SessionStatus.EMPTY,
            original_user_request=raw.get("original_user_request"),
            current_template_id=raw.get("current_template_id"),
            current_template_name=raw.get("current_template_name"),
            current_template_description=raw.get("current_template_description"),
            current_template_latex=raw.get("current_template_latex"),
            current_latex=raw.get("current_latex"),
            current_tex_path=raw.get("current_tex_path"),
            current_pdf_path=raw.get("current_pdf_path"),
            retrieval_results=retrieval_results,
            message_history=message_history,
            version=int(raw.get("version") or 0),
            last_error=raw.get("last_error"),
        )
