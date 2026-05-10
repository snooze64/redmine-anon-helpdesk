"""チャットセッションのメモリ内ストア。

プロセス再起動で消える簡易実装。本番化する際は Redis 等に置き換える。
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, Optional


SessionStatus = Literal["open", "closed", "escalated"]


@dataclass
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class ChatSession:
    session_id: str
    user_login: Optional[str] = None
    user_email: Optional[str] = None  # エスカレーション時の起票用
    turns: list[ChatTurn] = field(default_factory=list)
    status: SessionStatus = "open"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    escalated_issue_id: Optional[int] = None

    def add_turn(self, role: str, content: str, citations: list[dict] | None = None) -> ChatTurn:
        t = ChatTurn(role=role, content=content, citations=citations or [])
        self.turns.append(t)
        self.updated_at = time.time()
        return t

    def history_for_llm(self, limit_turns: int = 8) -> list[dict]:
        """LLM に渡す past messages の最新 N 往復だけを取り出す。"""
        recent = self.turns[-(limit_turns * 2):] if limit_turns > 0 else self.turns
        return [{"role": t.role, "content": t.content} for t in recent]


class SessionRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, ChatSession] = {}

    def create(self, user_login: str | None = None, user_email: str | None = None) -> ChatSession:
        sid = secrets.token_urlsafe(12)
        with self._lock:
            sess = ChatSession(session_id=sid, user_login=user_login, user_email=user_email)
            self._sessions[sid] = sess
            return sess

    def get(self, sid: str) -> ChatSession | None:
        with self._lock:
            return self._sessions.get(sid)

    def all(self) -> list[ChatSession]:
        with self._lock:
            return list(self._sessions.values())


_registry: SessionRegistry | None = None


def get_registry() -> SessionRegistry:
    global _registry
    if _registry is None:
        _registry = SessionRegistry()
    return _registry
