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
LOG_MAX_BYTES = 5 * 1024 * 1024  # 超过就滚动，保留最后一半，避免撑满 Volume
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
    with FeishuClient() as feishu:
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

        # 写回飞书也可能失败（网络/接口）——单独兜住并记账，否则会把一次成功的
        # 抓取变成上层的未捕获异常，且 scrape_log 里不会留下失败记录。
        try:
            feishu.update_record(record_id, result.fields)
        except Exception as exc:
            LOGGER.exception("update_record failed for %s", record_id)
            await _log(record_id, link, "error", f"update_record failed: {exc}", {})
            return {"status": "error", "message": str(exc)}

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
            _rotate_if_needed(p)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        LOGGER.warning("write log file failed: %s", exc)


def _rotate_if_needed(p: Path) -> None:
    """日志超过上限时，只保留后半部分（按行截断），防止无限增长撑满 /data。"""
    try:
        if not p.exists() or p.stat().st_size < LOG_MAX_BYTES:
            return
        with p.open("rb") as f:
            f.seek(-(LOG_MAX_BYTES // 2), 2)
            f.readline()  # 丢弃可能被截断的半行
            tail = f.read()
        tmp = p.with_suffix(p.suffix + ".rot")
        tmp.write_bytes(tail)
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("log rotate failed: %s", exc)


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
        try:
            with FeishuClient() as feishu:
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
