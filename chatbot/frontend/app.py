"""Streamlit ベースの簡易フロントエンド。

3 つの HITL アクション (クローズ / 継続 / エスカレーション) を
ボタンで操作できるチャット UI。
"""
import os

import httpx
import streamlit as st

CHATBOT_API = os.environ.get("CHATBOT_API_URL", "http://chatbot:8100")

st.set_page_config(page_title="Redmine Helpdesk Chatbot", page_icon="🤖", layout="centered")
st.title("🤖 Redmine ヘルプデスク Chatbot")
st.caption("Redmine の過去チケットを根拠に回答します。AI で解決しなければ Redmine へエスカレーションできます。")


# ---- セッション初期化 ----------------------------------------------------

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role":..., "content":..., "citations":[...] }]
if "status" not in st.session_state:
    st.session_state.status = "open"
if "escalation_result" not in st.session_state:
    st.session_state.escalation_result = None


def _ensure_session(user_login: str | None, user_email: str | None) -> None:
    if st.session_state.session_id:
        return
    payload = {}
    if user_login:
        payload["user_login"] = user_login
    if user_email:
        payload["user_email"] = user_email
    r = httpx.post(f"{CHATBOT_API}/sessions", json=payload, timeout=30.0)
    r.raise_for_status()
    st.session_state.session_id = r.json()["session_id"]


def _send_message(text: str) -> dict:
    sid = st.session_state.session_id
    r = httpx.post(
        f"{CHATBOT_API}/sessions/{sid}/messages",
        json={"message": text},
        timeout=300.0,
    )
    r.raise_for_status()
    return r.json()


def _close() -> None:
    sid = st.session_state.session_id
    if not sid:
        return
    httpx.post(f"{CHATBOT_API}/sessions/{sid}/close", timeout=10.0)
    st.session_state.status = "closed"


def _escalate(title_hint: str | None, is_private: bool) -> dict:
    sid = st.session_state.session_id
    payload = {"is_private": is_private}
    if title_hint:
        payload["title"] = title_hint[:255]
    r = httpx.post(
        f"{CHATBOT_API}/sessions/{sid}/escalate",
        json=payload,
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


# ---- サイドバー: ユーザー情報 + crawl ボタン ---------------------------

with st.sidebar:
    st.header("セッション設定")
    user_login = st.text_input(
        "あなたの ログインID (任意)",
        help="既に Redmine にアカウントがある場合のみ。空ならエスカレーション時に匿名 ID が自動発行されます。",
    )
    user_email = st.text_input("メールアドレス (任意)", placeholder="...@example.com")

    st.divider()
    st.caption("管理操作")
    if st.button("🔄 ベクトル DB を更新 (crawl)"):
        with st.spinner("Redmine から取込中..."):
            try:
                r = httpx.post(f"{CHATBOT_API}/crawl", json={}, timeout=600.0)
                r.raise_for_status()
                d = r.json()
                st.success(
                    f"取得 {d['fetched']} / 新規 {d['inserted']} / 更新 {d['updated']} / スキップ {d['skipped_unchanged']}"
                )
            except Exception as e:
                st.error(f"crawl 失敗: {e}")

    st.divider()
    st.caption("セッション状態")
    st.json({
        "session_id": st.session_state.session_id,
        "status": st.session_state.status,
        "messages": len(st.session_state.messages),
    })


# ---- 過去メッセージ表示 -------------------------------------------------

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        cites = m.get("citations") or []
        if cites:
            with st.expander(f"参照チケット {len(cites)} 件"):
                for c in cites:
                    st.markdown(
                        f"- **#{c['issue_id']}** [{c['subject']}]({c['url']}) "
                        f"  status=`{c['status']}` distance={c['distance']:.3f}"
                    )


# ---- 入力 + 操作ボタン --------------------------------------------------

if st.session_state.status == "closed":
    st.info("✅ チャットを終了しました。新しいセッションを始めるにはページをリロードしてください。")
    st.stop()

if st.session_state.status == "escalated":
    res = st.session_state.escalation_result or {}
    st.success(f"📨 Redmine にエスカレーション完了 — Issue #{res.get('issue_id')}")
    if res.get("user_password"):
        st.warning(
            f"あなたの新規ログイン情報:\n\n"
            f"- ログインID: `{res.get('user_login')}`\n"
            f"- パスワード: `{res.get('user_password')}` （※この画面を閉じると二度と表示されません）\n"
        )
    st.markdown(f"プロジェクト: `{res.get('project_identifier')}`")
    st.stop()


prompt = st.chat_input("質問を入力...")
if prompt:
    try:
        _ensure_session(user_login or None, user_email or None)
    except Exception as e:
        st.error(f"セッション開始失敗: {e}")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt, "citations": []})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("AI が考え中..."):
            try:
                res = _send_message(prompt)
            except Exception as e:
                st.error(f"AI 呼出失敗: {e}")
                st.stop()
        ans = res.get("answer", "")
        cites = res.get("citations") or []
        st.markdown(ans)
        if cites:
            with st.expander(f"参照チケット {len(cites)} 件"):
                for c in cites:
                    st.markdown(
                        f"- **#{c['issue_id']}** [{c['subject']}]({c['url']}) "
                        f"  status=`{c['status']}` distance={c['distance']:.3f}"
                    )
    st.session_state.messages.append({"role": "assistant", "content": ans, "citations": cites})


# ---- HITL 3 ボタン -----------------------------------------------------

if st.session_state.session_id and st.session_state.messages:
    st.divider()
    cols = st.columns(3)
    with cols[0]:
        if st.button("✅ クローズ\n（解決した）", use_container_width=True):
            _close()
            st.rerun()
    with cols[1]:
        st.caption("✏️ 継続したい場合は\nそのまま下に質問を入力")
    with cols[2]:
        with st.popover("📨 人にエスカレーション", use_container_width=True):
            st.write("解決しなかった内容を Redmine チケットとして起票します。")
            esc_title = st.text_input("チケット件名 (空ならセッション最初の発話を流用)")
            esc_private = st.checkbox("プライベートチケット (関係者のみ閲覧可)")
            if st.button("🚀 起票して人に依頼"):
                with st.spinner("Redmine に起票中..."):
                    try:
                        result = _escalate(esc_title or None, esc_private)
                    except Exception as e:
                        st.error(f"エスカレーション失敗: {e}")
                    else:
                        st.session_state.status = "escalated"
                        st.session_state.escalation_result = result
                        st.rerun()
