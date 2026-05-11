"""RAG パイプライン: 検索 → コンテキスト整形 → LLM 呼出。"""
from __future__ import annotations

from dataclasses import dataclass

from typing import Optional

from app.chain.llm import LLMConfig, chat as llm_chat
from app.config import settings
from app.store.embedder import embed_one
from app.store.vectorstore import get_store


SYSTEM_PROMPT = """あなたは Redmine のチケット情報を元に、ユーザーの問い合わせに答える日本語のヘルプデスク AI です。

ルール:
- 提供された参考チケット (CONTEXT) に書かれている情報のみを根拠に回答してください。
- 推測や一般論で補完しないでください。CONTEXT に答えが無ければ「過去のチケットからは判断できません。
  人に確認してください」と素直に答えてください。
- 回答は簡潔・箇条書き優先。最後に必ず参照したチケット番号を「参照: #N, #M」の形で示してください。
- ユーザーから「もっと詳しく」「他には」と聞かれたら、別の参考チケットを検討してから返してください。
"""


def _format_context(hits: list[dict]) -> str:
    """検索結果をプロンプト文字列に整形。"""
    blocks: list[str] = []
    for r in hits:
        md = r.get("metadata") or {}
        doc = r.get("document") or ""
        iid = md.get("issue_id", "?")
        status = md.get("status", "")
        url = md.get("url", "")
        blocks.append(
            f"--- ticket #{iid} (status={status}) {url}\n{doc}\n"
        )
    return "\n".join(blocks) if blocks else "(関連チケットなし)"


@dataclass
class RagAnswer:
    answer: str
    citations: list[dict]   # [{"issue_id":..., "subject":..., "url":...}]


def answer(
    question: str,
    history: list[dict] | None = None,
    top_k: int | None = None,
    llm_config: Optional[LLMConfig] = None,
) -> RagAnswer:
    """RAG で回答する。

    Args:
        question:   今回のユーザー発話
        history:    これまでの会話履歴 (role/content)。空ならこれが初回。
        top_k:      検索件数 (None なら settings.retrieval_top_k)
        llm_config: LLM プロバイダ・モデル・API キー等。None なら settings 既定。
    """
    k = top_k or settings.retrieval_top_k
    store = get_store()

    emb = embed_one(question)
    hits = store.query(emb, top_k=k)

    context = _format_context(hits)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # 検索コンテキストを system 直後の user メッセージとして渡す
    messages.append({
        "role": "user",
        "content": (
            f"以下は社内 Redmine から検索された参考チケットです。\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"---\n\n"
            f"これを踏まえて以降の質問に答えてください。"
        ),
    })

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": question})

    text = llm_chat(messages, cfg=llm_config)

    citations = []
    for r in hits:
        md = r.get("metadata") or {}
        citations.append({
            "issue_id": int(md.get("issue_id", 0)),
            "subject": str(md.get("subject", "")),
            "url": str(md.get("url", "")),
            "status": str(md.get("status", "")),
            "distance": float(r.get("distance", 0.0)),
        })

    return RagAnswer(answer=text, citations=citations)
