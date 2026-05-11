"""APScheduler で定期 crawl を回す。crawl_interval_minutes が 0 なら無効。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.store.pipeline import crawl_and_index

log = logging.getLogger("chatbot.scheduler")
_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    try:
        outcome = crawl_and_index()
        log.info(
            "scheduled crawl: fetched=%d inserted=%d updated=%d skipped=%d",
            outcome.fetched, outcome.inserted, outcome.updated, outcome.skipped_unchanged,
        )
    except Exception as e:
        log.warning("scheduled crawl failed: %s", e)


def start() -> None:
    global _scheduler
    if settings.crawl_interval_minutes <= 0:
        log.info("scheduler disabled (CRAWL_INTERVAL_MINUTES=0)")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _job,
        trigger="interval",
        minutes=settings.crawl_interval_minutes,
        id="periodic_crawl",
        replace_existing=True,
    )
    _scheduler.start()
    log.info("scheduler started: interval=%d min", settings.crawl_interval_minutes)


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
