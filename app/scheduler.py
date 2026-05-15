from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from app.config import get_settings
from app.runner import run_scan_all

LOGGER = logging.getLogger(__name__)


async def start() -> list[asyncio.Task]:
    s = get_settings()
    tasks: list[asyncio.Task] = []
    if s.enable_daily_scan:
        tasks.append(asyncio.create_task(_daily_scan_loop(), name="daily_scan"))
    return tasks


async def _daily_scan_loop() -> None:
    while True:
        hour = get_settings().daily_scan_hour_utc
        delay = _seconds_until_next(hour)
        LOGGER.info("daily scan scheduled in %.0fs (UTC %02d:00)", delay, hour)
        await asyncio.sleep(delay)
        try:
            await run_scan_all()
        except Exception as exc:
            LOGGER.exception("daily scan failed: %s", exc)


def _seconds_until_next(target_hour_utc: int) -> float:
    now = datetime.now(timezone.utc)
    target = datetime.combine(now.date(), time(hour=target_hour_utc, tzinfo=timezone.utc))
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()
