from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _normalize_username(username: str) -> str:
    return " ".join((username or "").strip().split()).casefold()


def _display_username(username: str) -> str:
    return " ".join((username or "").strip().split())


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    username: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ChatRecord:
    chat_id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chats_user_updated
                ON chats(user_id, updated_at DESC);
                """
            )

    @staticmethod
    def _user_from_row(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            created_at=_parse_datetime(str(row["created_at"])),
            updated_at=_parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _chat_from_row(row: sqlite3.Row) -> ChatRecord:
        return ChatRecord(
            chat_id=str(row["chat_id"]),
            user_id=str(row["user_id"]),
            title=str(row["title"]),
            created_at=_parse_datetime(str(row["created_at"])),
            updated_at=_parse_datetime(str(row["updated_at"])),
        )

    def login_or_create_user(self, username: str) -> UserRecord:
        cleaned = _display_username(username)
        normalized = _normalize_username(cleaned)
        if not cleaned:
            raise ValueError("Логин не может быть пустым.")

        now = utc_now_iso()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, username, created_at, updated_at
                FROM users
                WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()

            if row is not None:
                connection.execute(
                    """
                    UPDATE users
                    SET username = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (cleaned, now, row["user_id"]),
                )
                refreshed = connection.execute(
                    """
                    SELECT user_id, username, created_at, updated_at
                    FROM users
                    WHERE user_id = ?
                    """,
                    (row["user_id"],),
                ).fetchone()
                return self._user_from_row(refreshed)

            user_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO users (user_id, username, username_normalized, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, cleaned, normalized, now, now),
            )
            return UserRecord(
                user_id=user_id,
                username=cleaned,
                created_at=_parse_datetime(now),
                updated_at=_parse_datetime(now),
            )

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, username, created_at, updated_at
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return self._user_from_row(row) if row is not None else None

    def create_chat(self, user_id: str, title: str = "Новый чат") -> ChatRecord:
        if self.get_user(user_id) is None:
            raise KeyError("Пользователь не найден.")

        now = utc_now_iso()
        chat_id = str(uuid.uuid4())
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chats (chat_id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, title, now, now),
            )

        return ChatRecord(
            chat_id=chat_id,
            user_id=user_id,
            title=title,
            created_at=_parse_datetime(now),
            updated_at=_parse_datetime(now),
        )

    def list_chats(self, user_id: str) -> list[ChatRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chat_id, user_id, title, created_at, updated_at
                FROM chats
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._chat_from_row(row) for row in rows]

    def get_chat(self, user_id: str, chat_id: str) -> ChatRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT chat_id, user_id, title, created_at, updated_at
                FROM chats
                WHERE user_id = ? AND chat_id = ?
                """,
                (user_id, chat_id),
            ).fetchone()
        return self._chat_from_row(row) if row is not None else None

    def delete_chat(self, user_id: str, chat_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM chats
                WHERE user_id = ? AND chat_id = ?
                """,
                (user_id, chat_id),
            )
        return cursor.rowcount > 0

    def touch_chat(self, user_id: str, chat_id: str) -> None:
        now = utc_now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET updated_at = ?
                WHERE user_id = ? AND chat_id = ?
                """,
                (now, user_id, chat_id),
            )

    def update_title_if_default(self, user_id: str, chat_id: str, user_message: str) -> None:
        chat = self.get_chat(user_id, chat_id)
        if chat is None or chat.title != "Новый чат":
            return

        cleaned = " ".join((user_message or "").strip().split())
        if not cleaned:
            return

        now = utc_now_iso()
        title = cleaned[:60]
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE chats
                SET title = ?, updated_at = ?
                WHERE user_id = ? AND chat_id = ?
                """,
                (title, now, user_id, chat_id),
            )
