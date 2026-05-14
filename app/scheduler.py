from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time, timedelta, timezone

from app.runner import keepalive_ping, run_scan_all

LOGGER = logging.getLogger(__name__)

KEEPALIVE_INTERVAL = timedelta(days=2)
DAILY_SCAN_HOUR_UTC = int(os.getenv("DAILY_SCAN_HOUR_UTC", "20"))  # 默认 UTC 20:00 = 北京 04:00
ENABLE_DAILY_SCAN = os.getenv("ENABLE_DAILY_SCAN", "1") not in ("0", "false", "False", "")


async def start() -> list[asyncio.Task]:
    tasks: list[asyncio.Task] = [asyncio.create_task(_keepalive_loop(), name="keepalive")]
    if ENABLE_DAILY_SCAN:
        tasks.append(asyncio.create_task(_daily_scan_loop(), name="daily_scan"))
    return tasks


async def _keepalive_loop() -> None:
    while True:
        try:
            await keepalive_ping()
        except Exception as exc:
            LOGGER.warning("keepalive failed: %s", exc)
        await asyncio.sleep(KEEPALIVE_INTERVAL.total_seconds())


async def _daily_scan_loop() -> None:
    while True:
        delay = _seconds_until_next(DAILY_SCAN_HOUR_UTC)
        LOGGER.info("daily scan scheduled in %.0fs", delay)
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
