from __future__ import annotations

from queue import Queue
from threading import Lock
from typing import Dict, Optional

from .schema import ChatMessage, MessageRole, SessionState, SessionStatus


class SessionStateManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._subscribers: Dict[str, list[Queue]] = {}
        self._subscribers_lock = Lock()

    def get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    def reset(self, session_id: str) -> SessionState:
        state = SessionState(session_id=session_id)
        self._sessions[session_id] = state
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
