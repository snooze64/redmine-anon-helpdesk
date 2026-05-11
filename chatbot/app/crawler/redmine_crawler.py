"""Redmine からチケットを取得してチャンク化する。

仕様:
  - 1 チケット = 1 チャンク (subject + description + journal の連結テキスト)
  - 全状態 (open / closed) を取得
  - メタデータ (issue_id / status / tracker / 更新日 等) を併せて返す
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from redminelib import Redmine

from app.config import settings


@dataclass
class TicketChunk:
    """1 チケット = 1 チャンク。ベクトル DB に投入する単位。"""

    issue_id: int
    text: str
    metadata: dict = field(default_factory=dict)


def _format_ticket_text(issue, include_journals: bool) -> str:
    """1 チケットを 1 つのテキストブロックに整形。

    形式 (Markdown 風):
        # <subject>

        Status: <status>  Tracker: <tracker>  Priority: <priority>
        Author: <login>  Assigned to: <login or '-'>

        ## Description
        <description>

        ## Comment 1 (login, date)
        <notes>
        ...
    """
    lines: list[str] = []

    subject = getattr(issue, "subject", "") or ""
    lines.append(f"# {subject}")
    lines.append("")

    # 1 行サマリ (検索ヒット時にスニペット化しやすく)
    status = getattr(issue.status, "name", "") if getattr(issue, "status", None) else ""
    tracker = getattr(issue.tracker, "name", "") if getattr(issue, "tracker", None) else ""
    priority = getattr(issue.priority, "name", "") if getattr(issue, "priority", None) else ""
    author_login = ""
    try:
        author_login = issue.author.login if getattr(issue, "author", None) else ""
    except Exception:
        pass
    assigned_login = "-"
    try:
        assigned_login = (
            issue.assigned_to.login if getattr(issue, "assigned_to", None) else "-"
        )
    except Exception:
        pass

    lines.append(
        f"Status: {status}  Tracker: {tracker}  Priority: {priority}"
    )
    lines.append(f"Author: {author_login}  Assigned to: {assigned_login}")
    lines.append("")

    description = getattr(issue, "description", "") or ""
    if description.strip():
        lines.append("## Description")
        lines.append(description)
        lines.append("")

    if include_journals:
        try:
            journals = list(getattr(issue, "journals", []) or [])
        except Exception:
            journals = []
        n = 0
        for j in journals:
            notes = getattr(j, "notes", "") or ""
            if not notes.strip():
                continue
            n += 1
            j_user = ""
            try:
                j_user = j.user.login if getattr(j, "user", None) else ""
            except Exception:
                pass
            j_date = getattr(j, "created_on", "") or ""
            lines.append(f"## Comment {n} ({j_user}, {j_date})")
            lines.append(notes)
            lines.append("")

    return "\n".join(lines).strip()


def _build_metadata(issue) -> dict:
    """ChromaDB メタデータ用に Issue から JSON-serializable な dict を作る。

    ChromaDB は str / int / float / bool しか metadata 値に許容しないので、
    日付や名前は str に潰す。
    """
    def safe(obj, attr, default=""):
        try:
            v = getattr(obj, attr, default)
            return v if v is not None else default
        except Exception:
            return default

    def safe_name(rel):
        try:
            return rel.name if rel and hasattr(rel, "name") else ""
        except Exception:
            return ""

    def safe_login(rel):
        try:
            return rel.login if rel and hasattr(rel, "login") else ""
        except Exception:
            return ""

    status = getattr(issue, "status", None)
    tracker = getattr(issue, "tracker", None)
    priority = getattr(issue, "priority", None)
    project = getattr(issue, "project", None)
    author = getattr(issue, "author", None)
    assigned_to = getattr(issue, "assigned_to", None)

    is_closed = False
    try:
        is_closed = bool(getattr(status, "is_closed", False))
    except Exception:
        pass

    md: dict = {
        "issue_id": int(issue.id),
        "subject": str(safe(issue, "subject", "")),
        "project_id": int(safe(project, "id", 0)) if project else 0,
        "project_identifier": str(safe(project, "identifier", "")) if project else "",
        "tracker": safe_name(tracker),
        "status": safe_name(status),
        "is_closed": is_closed,
        "priority": safe_name(priority),
        "author_login": safe_login(author),
        "assigned_login": safe_login(assigned_to),
        "is_private": bool(getattr(issue, "is_private", False)),
        "created_on": str(safe(issue, "created_on", "")),
        "updated_on": str(safe(issue, "updated_on", "")),
        # citation 用には外部 URL を使う (ブラウザがアクセスできる URL)
        "url": f"{settings.redmine_public_url.rstrip('/')}/issues/{issue.id}",
    }
    return md


def fetch_all_tickets(rm: Redmine, project_identifier: str) -> Iterable:
    """指定プロジェクトの全状態 (open + closed) のチケットを yield。

    python-redmine の filter は ResourceSet を返し、自動でページネーション
    する (limit/offset 透過)。status_id='*' で全ステータス。
    """
    includes = ["journals"] if settings.crawl_include_journals else []
    return rm.issue.filter(
        project_id=project_identifier,
        status_id="*",
        include=",".join(includes) if includes else None,
        sort="updated_on:desc",
    )


def crawl(
    rm: Redmine,
    project_identifier: Optional[str] = None,
    since_updated_on: Optional[str] = None,
) -> list[TicketChunk]:
    """対象プロジェクトのチケットを取得 → TicketChunk のリスト。

    Args:
        project_identifier: 対象プロジェクト identifier (空なら settings の既定)
        since_updated_on: '2026-05-01T00:00:00Z' のような ISO 文字列。
                          指定すると updated_on がそれ以降のチケットだけ返す
                          (差分 crawl 用フィルタ。実装は filter 後の Python 側比較)
    """
    proj = project_identifier or settings.crawl_project_identifier
    chunks: list[TicketChunk] = []

    for issue in fetch_all_tickets(rm, proj):
        if since_updated_on:
            updated = str(getattr(issue, "updated_on", "") or "")
            if updated and updated <= since_updated_on:
                # ISO 8601 文字列同士は辞書順で時系列比較できる
                continue

        text = _format_ticket_text(issue, include_journals=settings.crawl_include_journals)
        md = _build_metadata(issue)
        chunks.append(TicketChunk(issue_id=int(issue.id), text=text, metadata=md))

    return chunks
