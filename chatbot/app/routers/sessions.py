from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.chain.llm import LLMError
from app.chain.rag import answer as rag_answer
from app.session.escalate import EscalationError, escalate
from app.session.store import ChatSession, get_registry

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---- 入出力モデル ---------------------------------------------------------

class CreateSessionRequest(BaseModel):
    user_login: Optional[str] = Field(
        None, description="質問者の Redmine ログインID。未指定なら匿名 (escalate 時に自動生成)"
    )
    user_email: Optional[str] = Field(None, description="エスカレーション時の通知先メール")


class SessionView(BaseModel):
    session_id: str
    status: str
    turns: int
    user_login: Optional[str] = None
    escalated_issue_id: Optional[int] = None


class PostMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)


class Citation(BaseModel):
    issue_id: int
    subject: str
    url: str
    status: str
    distance: float


class PostMessageResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]


class EscalateRequest(BaseModel):
    title: Optional[str] = Field(
        None, description="チケット件名。未指定ならセッション最初のユーザー発話を流用 (255 文字に丸め)"
    )
    description: Optional[str] = Field(
        None, description="チケット本文。未指定ならセッション履歴を整形して投入"
    )
    is_private: bool = False
    user_login: Optional[str] = Field(None, description="セッション作成時に未指定なら今ここで指定可")
    user_email: Optional[str] = None


class EscalateResponse(BaseModel):
    session_id: str
    status: str
    issue_id: int
    project_identifier: str
    user_login: str
    user_password: Optional[str] = Field(
        None, description="新規ユーザーが作成された場合のみ返却 (既存ユーザーなら null)"
    )


# ---- ヘルパ --------------------------------------------------------------

def _view(s: ChatSession) -> SessionView:
    return SessionView(
        session_id=s.session_id,
        status=s.status,
        turns=len(s.turns),
        user_login=s.user_login,
        escalated_issue_id=s.escalated_issue_id,
    )


def _require_open_session(sid: str) -> ChatSession:
    s = get_registry().get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    if s.status != "open":
        raise HTTPException(status_code=409, detail=f"session is {s.status}")
    return s


# ---- エンドポイント ------------------------------------------------------

@router.post("", response_model=SessionView, summary="新規チャットセッション開始")
def create_session(req: Optional[CreateSessionRequest] = None) -> SessionView:
    req = req or CreateSessionRequest()
    s = get_registry().create(user_login=req.user_login, user_email=req.user_email)
    return _view(s)


@router.get("/{session_id}", response_model=SessionView)
def get_session(session_id: str) -> SessionView:
    s = get_registry().get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _view(s)


@router.post(
    "/{session_id}/messages",
    response_model=PostMessageResponse,
    summary="ユーザー発話を投げて RAG 回答を得る",
)
def post_message(session_id: str, req: PostMessageRequest) -> PostMessageResponse:
    s = _require_open_session(session_id)
    s.add_turn("user", req.message)
    try:
        history = s.history_for_llm(limit_turns=4)
        # 直近に追加した user メッセージは history 末尾に入っているので、rag_answer に
        # 入れる history からは除外し、question として渡す
        ans = rag_answer(question=req.message, history=history[:-1])
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RAG error: {type(e).__name__}: {e}") from e

    s.add_turn("assistant", ans.answer, citations=ans.citations)
    return PostMessageResponse(
        session_id=session_id,
        answer=ans.answer,
        citations=[Citation(**c) for c in ans.citations],
    )


@router.post("/{session_id}/close", response_model=SessionView, summary="セッションを閉じる")
def close_session(session_id: str) -> SessionView:
    s = _require_open_session(session_id)
    s.status = "closed"
    return _view(s)


@router.post(
    "/{session_id}/continue",
    response_model=SessionView,
    summary="(no-op) 継続意思を明示するためのエンドポイント",
)
def continue_session(session_id: str) -> SessionView:
    """フロントから明示的に「継続」を選んだことを記録する用途。
    実際は次の POST /sessions/{id}/messages を投げれば継続しているのと同じ。
    """
    s = _require_open_session(session_id)
    return _view(s)


@router.post(
    "/{session_id}/escalate",
    response_model=EscalateResponse,
    summary="人にエスカレーション → Redmine にチケット起票",
)
def escalate_session(session_id: str, req: Optional[EscalateRequest] = None) -> EscalateResponse:
    s = _require_open_session(session_id)
    req = req or EscalateRequest()

    # 質問者情報の解決
    user_login = req.user_login or s.user_login
    user_email = req.user_email or s.user_email

    # 件名: 明示が無ければセッション最初のユーザー発話を使う
    title = req.title
    if not title:
        first_user = next((t for t in s.turns if t.role == "user"), None)
        if first_user:
            title = first_user.content.strip().splitlines()[0][:255] if first_user.content.strip() else "(no subject)"
        else:
            title = "(no subject)"

    # 本文: 明示が無ければ会話ログを Markdown 化
    description = req.description
    if not description:
        lines = ["## チャットボット会話履歴", ""]
        for i, t in enumerate(s.turns, 1):
            who = "ユーザー" if t.role == "user" else "AI"
            lines.append(f"### {i}. {who}")
            lines.append(t.content)
            lines.append("")
        description = "\n".join(lines)

    try:
        result = escalate(
            user_login=user_login,
            user_email=user_email,
            title=title,
            description=description,
            is_private=req.is_private,
        )
    except EscalationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Escalate error: {type(e).__name__}: {e}") from e

    s.status = "escalated"
    s.user_login = result.user_login
    s.escalated_issue_id = result.issue_id

    return EscalateResponse(
        session_id=session_id,
        status="escalated",
        issue_id=result.issue_id,
        project_identifier=result.project_identifier,
        user_login=result.user_login,
        user_password=result.user_password,
    )
