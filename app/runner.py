from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.feishu import FeishuClient, extract_link
from app.scraper import LoginRequired, scrape

LOGGER = logging.getLogger(__name__)

LOG_FILENAME = "scrape_log.jsonl"
_log_lock = asyncio.Lock()

_scan_lock = asyncio.Lock()
_scan_status: dict[str, Any] = {
    "state": "idle",
    "total": 0,
    "done": 0,
    "ok": 0,
    "skipped": 0,
    "errors": 0,
    "started_at": None,
    "finished_at": None,
    "last_error": None,
}


def scan_status() -> dict:
    return dict(_scan_status)


def log_path() -> Path:
    return Path(get_settings().state_dir) / LOG_FILENAME


async def run_for_record(record_id: str) -> dict:
    s = get_settings()
    feishu = FeishuClient()
    record = feishu.get_record(record_id)
    link = extract_link(record, s.link_field_name)
    if not link:
        await _log(record_id, None, "skipped", "频道链接列为空", {})
        return {"status": "skipped", "reason": "missing-link"}

    try:
        result = await scrape(link)
    except LoginRequired as exc:
        await _log(record_id, link, "login_required", str(exc), {})
        return {"status": "login_required", "message": str(exc)}
    except Exception as exc:
        LOGGER.exception("scrape failed for %s", link)
        await _log(record_id, link, "error", str(exc), {})
        return {"status": "error", "message": str(exc)}

    feishu.update_record(record_id, result.fields)
    payload = {"fields": result.fields, "missing": result.missing}
    await _log(
        record_id,
        link,
        "ok" if not result.missing else "partial",
        "",
        payload,
    )
    return {"status": "ok", **payload}


async def _log(
    record_id: Optional[str],
    link: Optional[str],
    status: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "record_id": record_id,
        "url": link,
        "status": status,
        "message": message,
        "payload": payload,
    }
    LOGGER.info(
        "scrape status=%s record=%s url=%s msg=%s",
        status,
        record_id,
        link,
        message,
    )
    p = log_path()
    try:
        async with _log_lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        LOGGER.warning("write log file failed: %s", exc)


SCAN_DELAY_SECONDS = 1.0


async def run_scan_all(*, delay_seconds: Optional[float] = None) -> dict:
    if _scan_lock.locked():
        return {"status": "already_running", **scan_status()}
    delay = delay_seconds if delay_seconds is not None else SCAN_DELAY_SECONDS

    async with _scan_lock:
        _scan_status.update(
            state="running",
            total=0,
            done=0,
            ok=0,
            skipped=0,
            errors=0,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            last_error=None,
        )
        feishu = FeishuClient()
        try:
            items = feishu.list_records()
        except Exception as exc:
            LOGGER.exception("list_records failed")
            _scan_status.update(
                state="error",
                last_error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            await _log(None, None, "error", f"list_records failed: {exc}", {})
            return {"status": "error", **scan_status()}

        _scan_status["total"] = len(items)
        await _log(None, None, "scan_start", f"total={len(items)}", {"total": len(items)})

        for record in items:
            record_id = record.get("record_id") or record.get("id")
            if not record_id:
                _scan_status["skipped"] += 1
                _scan_status["done"] += 1
                continue
            try:
                result = await run_for_record(record_id)
                status = result.get("status")
                if status == "ok":
                    _scan_status["ok"] += 1
                elif status == "skipped":
                    _scan_status["skipped"] += 1
                else:
                    _scan_status["errors"] += 1
                    _scan_status["last_error"] = result.get("message")
            except Exception as exc:
                LOGGER.exception("run_for_record failed for %s", record_id)
                _scan_status["errors"] += 1
                _scan_status["last_error"] = str(exc)
            _scan_status["done"] += 1
            if delay > 0:
                await asyncio.sleep(delay)

        _scan_status.update(state="done", finished_at=datetime.now(timezone.utc).isoformat())
        await _log(None, None, "scan_done", "scan_all finished", scan_status())
        return {"status": "ok", **scan_status()}


def tail_log(n: int = 100) -> list[dict]:
    p = log_path()
    if not p.exists():
        return []
    from collections import deque

    with p.open("r", encoding="utf-8") as f:
        lines = list(deque(f, maxlen=max(1, n)))
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": line})
    return out
