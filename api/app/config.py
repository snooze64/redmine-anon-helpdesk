from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数から読み込む設定。docker-compose 側で渡される値を受ける。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Redmine 接続 -----
    redmine_url: str = "http://redmine:3000"
    redmine_api_key: str = ""
    redmine_admin_username: str = ""
    redmine_admin_password: str = ""

    # ----- 質問者アカウント作成時の既定値 -----
    questioner_project_identifier: str = "demo"  # Redmine の Project identifier
    questioner_role_name: str = "質問者"           # Redmine のロール名 (完全一致)
    questioner_language: str = "ja"               # Redmine User#language

    # ----- 問い合わせチケット作成時の既定値 -----
    # チケットを起票するプロジェクト (空ならアカウント作成と同じ既定プロジェクト)
    inquiry_project_identifier: str = ""
    # 利用するトラッカー名 (例: 'サポート' / 'Support'。空ならプロジェクトの先頭トラッカー)
    inquiry_tracker_name: str = ""
    # 起票時にウォッチャーへ自動追加する「回答者」ロール名 (完全一致)
    # このロールをプロジェクトに持つメンバー全員が watcher になる
    responder_role_name: str = "回答者"
    # 起票を Redmine 上「質問者本人」として行うか (impersonation)。
    # True にすると author = 質問者 になり、質問者ロールに `add_issues` 権限が
    # 必要 (docs/manual_setup.md 参照)。
    # False の場合は admin が author になるため、is_private=True のチケットは
    # 質問者本人からも閲覧できなくなる。
    create_ticket_as_questioner: bool = True
    # 起票時に「チャットボット起票」を識別するためのカスタムフィールド ID。
    # 0 なら無効化 (カスタムフィールドを使わない)。
    # 該当カスタムフィールドの作成手順は docs/manual_setup.md 参照。
    chatbot_session_custom_field_id: int = 0


settings = Settings()
