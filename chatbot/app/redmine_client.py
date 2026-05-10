"""Redmine 接続用 python-redmine クライアント生成。"""
from redminelib import Redmine

from app.config import settings


class RedmineNotConfigured(RuntimeError):
    pass


def get_redmine() -> Redmine:
    if settings.redmine_api_key:
        return Redmine(settings.redmine_url, key=settings.redmine_api_key)
    if settings.redmine_admin_username and settings.redmine_admin_password:
        return Redmine(
            settings.redmine_url,
            username=settings.redmine_admin_username,
            password=settings.redmine_admin_password,
        )
    raise RedmineNotConfigured(
        "REDMINE_API_KEY または REDMINE_ADMIN_USERNAME/PASSWORD を .env に設定してください。"
    )
