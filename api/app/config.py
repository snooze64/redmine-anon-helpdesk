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


settings = Settings()
