from redminelib import Redmine

from app.config import settings


class RedmineNotConfigured(RuntimeError):
    """API key も admin 認証情報も設定されていないとき送出。"""


def get_redmine() -> Redmine:
    """設定済みの python-redmine クライアントを返す。

    優先順:
      1. REDMINE_API_KEY (推奨)
      2. REDMINE_ADMIN_USERNAME + REDMINE_ADMIN_PASSWORD (フォールバック)
    """
    if settings.redmine_api_key:
        return Redmine(settings.redmine_url, key=settings.redmine_api_key)

    if settings.redmine_admin_username and settings.redmine_admin_password:
        return Redmine(
            settings.redmine_url,
            username=settings.redmine_admin_username,
            password=settings.redmine_admin_password,
        )

    raise RedmineNotConfigured(
        "Redmine 認証が未設定です。"
        "REDMINE_API_KEY または REDMINE_ADMIN_USERNAME/REDMINE_ADMIN_PASSWORD を .env に設定してください。"
    )


def get_redmine_as(login: str) -> Redmine:
    """admin の認証情報を使いつつ、X-Redmine-Switch-User ヘッダで他ユーザーに
    なりすました Redmine クライアントを返す。

    用途:
      - チャットボットが質問者 (login) のチケットを起票するとき、Redmine 上の
        author を質問者本人にしたい (admin ではなく) → 質問者は自分の private
        チケットを author rule で閲覧可能になる。

    制約:
      - 認証主体 (= admin) は impersonation 権限が必要 (Redmine 管理者である
        こと)。それ以外のユーザーで API key を出した場合は使えない。
      - **権限チェックはなりすました先 (login) で行われる**。たとえば issue
        作成なら、login のユーザーが `add_issues` 権限を該当プロジェクトで
        持っていなければ 403 になる。
    """
    if not login or not login.strip():
        raise RedmineNotConfigured("impersonate 先のログイン ID が空です。")

    if settings.redmine_api_key:
        return Redmine(
            settings.redmine_url,
            key=settings.redmine_api_key,
            impersonate=login,
        )
    if settings.redmine_admin_username and settings.redmine_admin_password:
        return Redmine(
            settings.redmine_url,
            username=settings.redmine_admin_username,
            password=settings.redmine_admin_password,
            impersonate=login,
        )

    raise RedmineNotConfigured(
        "Redmine 認証が未設定です。"
        "REDMINE_API_KEY または REDMINE_ADMIN_USERNAME/REDMINE_ADMIN_PASSWORD を .env に設定してください。"
    )
