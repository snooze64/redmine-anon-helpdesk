"""Streamlit ベースの簡易フロントエンド。

LLM プロバイダ・モデル・API キー (OpenAI 用) を UI 上で切り替えられる。
3 つの HITL アクション (クローズ / 継続 / エスカレーション) ボタン付き。
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
    st.session_state.messages = []
if "status" not in st.session_state:
    st.session_state.status = "open"
if "escalation_result" not in st.session_state:
    st.session_state.escalation_result = None
if "models_cache" not in st.session_state:
    st.session_state.models_cache = None


# ---- バックエンド呼出ヘルパ ---------------------------------------------

def _fetch_models() -> dict:
    if st.session_state.models_cache is not None:
        return st.session_state.models_cache
    try:
        r = httpx.get(f"{CHATBOT_API}/models", timeout=5.0)
        r.raise_for_status()
        st.session_state.models_cache = r.json()
    except Exception:
        st.session_state.models_cache = {
            "providers": ["ollama", "openai"],
            "ollama_default": "qwen2.5:7b",
            "ollama_installed": [],
            "ollama_suggestions": ["qwen2.5:7b", "qwen2.5:0.5b"],
            "openai_default": "gpt-4o-mini",
            "openai_suggestions": ["gpt-4o-mini", "gpt-4o"],
            "openai_base_url_default": "",
        }
    return st.session_state.models_cache


def _ensure_session(
    user_login: str | None, user_email: str | None,
    provider: str | None, model: str | None, api_key: str | None,
    base_url: str | None = None,
) -> None:
    if st.session_state.session_id:
        return
    payload: dict = {}
    if user_login:
        payload["user_login"] = user_login
    if user_email:
        payload["user_email"] = user_email
    if provider:
        payload["llm_provider"] = provider
    if model:
        payload["llm_model"] = model
    if api_key:
        payload["llm_api_key"] = api_key
    if base_url:
        payload["llm_base_url"] = base_url
    r = httpx.post(f"{CHATBOT_API}/sessions", json=payload, timeout=30.0)
    r.raise_for_status()
    st.session_state.session_id = r.json()["session_id"]


def _send_message(text: str) -> dict:
    sid = st.session_state.session_id
    r = httpx.post(
        f"{CHATBOT_API}/sessions/{sid}/messages",
        json={"message": text},
        timeout=600.0,
    )
    r.raise_for_status()
    return r.json()


def _close() -> None:
    sid = st.session_state.session_id
    if not sid:
        return
    httpx.post(f"{CHATBOT_API}/sessions/{sid}/close", timeout=10.0)
    st.session_state.status = "closed"


def _escalate(
    title_hint: str | None, is_private: bool, user_email: str,
) -> dict:
    sid = st.session_state.session_id
    payload: dict = {"is_private": is_private, "user_email": user_email}
    if title_hint:
        payload["title"] = title_hint[:255]
    r = httpx.post(
        f"{CHATBOT_API}/sessions/{sid}/escalate", json=payload, timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


# ---- サイドバー: ユーザー + LLM 設定 + 管理 ----------------------------

with st.sidebar:
    st.header("🔧 LLM 設定")

    models = _fetch_models()

    # セッション開始済みなら provider/model は変更不可（誤動作回避）
    locked = st.session_state.session_id is not None

    llm_provider: str
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    provider_choice = st.radio(
        "プロバイダ",
        ["ollama", "openai"],
        index=0,
        horizontal=True,
        disabled=locked,
        format_func=lambda x: "🦙 Ollama (ローカル)" if x == "ollama" else "🤖 OpenAI",
        help="セッション開始後は変更不可。切り替えたい場合は「セッションをリセット」してから。",
    )

    if provider_choice == "ollama":
        st.caption("ローカルの Ollama サーバーで推論。API キー不要。")
        # Ollama: 既に pull 済みのモデルを優先表示
        installed = models.get("ollama_installed", [])
        suggestions = models.get("ollama_suggestions", [])
        # union を順番維持で
        seen = set()
        ollama_options: list[str] = []
        for n in installed + suggestions:
            if n not in seen:
                seen.add(n)
                ollama_options.append(n)
        if not ollama_options:
            ollama_options = [models.get("ollama_default", "qwen2.5:7b")]

        default_idx = 0
        if models.get("ollama_default") in ollama_options:
            default_idx = ollama_options.index(models["ollama_default"])

        llm_provider = "ollama"
        llm_model = st.selectbox(
            "Ollama モデル",
            ollama_options,
            index=default_idx,
            disabled=locked,
            help="✅ マークが付くのは Ollama サーバーに既に pull 済のもの",
            format_func=lambda x: f"✅ {x}" if x in installed else f"   {x}  (未 pull)",
        )
        llm_api_key = None
    else:
        st.caption(
            "OpenAI API または OpenAI 互換 API (Azure OpenAI / 社内 LLM ゲートウェイ / "
            "LiteLLM / vLLM 等) で推論。API キーがこのブラウザに送信されます。"
        )
        openai_options = models.get("openai_suggestions", ["gpt-4o-mini"])
        oai_default_idx = 0
        if models.get("openai_default") in openai_options:
            oai_default_idx = openai_options.index(models["openai_default"])

        llm_provider = "openai"
        llm_model = st.selectbox(
            "OpenAI モデル",
            openai_options,
            index=oai_default_idx,
            disabled=locked,
            help=(
                "互換 API を使う場合は、その API が受け付けるモデル名を直接入力してもよいが、"
                "現状はリストからの選択のみ。必要なら settings の OPENAI_LLM_SUGGESTIONS で候補追加可能。"
            ),
        )
        openai_key_input = st.text_input(
            "OpenAI API キー",
            type="password",
            placeholder="sk-... ",
            disabled=locked,
            help="セッション中のみメモリに保持されます。Redmine リポジトリには保存されません。",
        )
        llm_api_key = openai_key_input.strip() or None

        # OpenAI 互換 API の base URL (任意)
        base_url_default = models.get("openai_base_url_default", "") or ""
        base_url_input = st.text_input(
            "Base URL (任意)",
            value=base_url_default,
            placeholder="https://api.openai.com/v1 (空なら公式 OpenAI)",
            disabled=locked,
            help=(
                "OpenAI 互換 API のエンドポイント。例:\n"
                "  - 公式 OpenAI: 空のまま (https://api.openai.com/v1 が使われる)\n"
                "  - 社内 LLM ゲートウェイ: https://my-gw.example.com/v1\n"
                "  - LiteLLM Proxy: http://litellm:4000/v1\n"
                "  - ローカル vLLM: http://localhost:8000/v1"
            ),
        )
        llm_base_url = base_url_input.strip() or None

    if locked:
        info_lines = [
            f"現在のセッション: **{st.session_state.session_id[:8]}…**",
            "",
            f"provider=`{llm_provider}`  model=`{llm_model}`",
        ]
        if llm_provider == "openai" and llm_base_url:
            info_lines.append(f"base_url=`{llm_base_url}`")
        st.info("\n".join(info_lines))

    st.divider()
    st.header("👤 質問者情報")
    st.caption(
        "ここでの入力は任意 (チャットだけならメールアドレスも不要)。"
        "エスカレーション (起票) するときには必ずメールアドレスが必要になります。"
    )
    user_login = st.text_input(
        "ログインID (任意)",
        help="既に Redmine にアカウントがある場合のみ。空ならエスカレーション時に email から派生した匿名 ID が使われます。",
        disabled=locked,
    )
    user_email = st.text_input(
        "メールアドレス",
        placeholder="...@example.com",
        disabled=locked,
        help=(
            "エスカレーション時に必須。先にここで入れておくと起票画面の初期値として"
            "入ります。同じメールアドレスは Redmine 上で同じアカウントに名寄せされる"
            "ので、複数回起票してもアカウントは増えません。"
        ),
    )

    st.divider()
    st.header("⚙️ 管理操作")
    if st.button("🔄 ベクトル DB を更新 (crawl)"):
        with st.spinner("Redmine から取込中..."):
            try:
                r = httpx.post(f"{CHATBOT_API}/crawl", json={}, timeout=600.0)
                r.raise_for_status()
                d = r.json()
                st.success(
                    f"取得 {d['fetched']}"
                    f" / 新規 {d['inserted']}"
                    f" / 更新 {d['updated']}"
                    f" / 削除 {d.get('deleted', 0)}"
                    f" / スキップ(変更なし) {d['skipped_unchanged']}"
                    f" / スキップ(private) {d.get('skipped_private', 0)}"
                )
            except Exception as e:
                st.error(f"crawl 失敗: {e}")

    if st.button("🔁 セッションをリセット"):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.session_state.status = "open"
        st.session_state.escalation_result = None
        st.rerun()


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


# ---- 終了 / エスカレーション 表示 ----------------------------------------

if st.session_state.status == "closed":
    st.info("✅ チャットを終了しました。サイドバーの「セッションをリセット」で新しい会話を始められます。")
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


# ---- 入力 + 操作ボタン --------------------------------------------------

prompt = st.chat_input("質問を入力...")
if prompt:
    # OpenAI を選んだのに API キー未入力 → 早期エラー
    if llm_provider == "openai" and not llm_api_key:
        st.error("OpenAI を選択するなら API キーをサイドバーで入力してください。")
        st.stop()

    try:
        _ensure_session(
            user_login or None, user_email or None,
            llm_provider, llm_model, llm_api_key,
            base_url=llm_base_url,
        )
    except httpx.HTTPStatusError as e:
        st.error(f"セッション開始失敗: HTTP {e.response.status_code} {e.response.text[:200]}")
        st.stop()
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
            except httpx.HTTPStatusError as e:
                st.error(f"AI 呼出失敗: HTTP {e.response.status_code} {e.response.text[:300]}")
                st.stop()
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
            esc_email = st.text_input(
                "メールアドレス ※必須",
                value=user_email or "",
                placeholder="...@example.com",
                help=(
                    "同じメールアドレスからのエスカレーションは Redmine 上で"
                    "同じアカウントに名寄せされます (毎回新規アカウントが"
                    "増えないように)。担当者からの連絡もこの宛先に届きます。"
                ),
            )
            esc_title = st.text_input("チケット件名 (空ならセッション最初の発話を流用)")
            esc_private = st.checkbox("プライベートチケット (関係者のみ閲覧可)")
            if st.button("🚀 起票して人に依頼"):
                if not esc_email.strip():
                    st.error("メールアドレスは必須です。入力してください。")
                else:
                    with st.spinner("Redmine に起票中..."):
                        try:
                            result = _escalate(
                                esc_title or None, esc_private, esc_email.strip(),
                            )
                        except Exception as e:
                            st.error(f"エスカレーション失敗: {e}")
                        else:
                            st.session_state.status = "escalated"
                            st.session_state.escalation_result = result
                            st.rerun()
