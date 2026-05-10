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
