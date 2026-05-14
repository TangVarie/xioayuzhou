from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.feishu import FeishuClient, extract_link
from app.scraper import LoginRequired, scrape
from app.supabase_client import supabase

LOGGER = logging.getLogger(__name__)


async def run_for_record(record_id: str) -> dict:
    s = get_settings()
    feishu = FeishuClient()
    record = feishu.get_record(record_id)
    link = extract_link(record, s.link_field_name)
    if not link:
        _log(record_id, None, "skipped", "频道链接列为空", {})
        return {"status": "skipped", "reason": "missing-link"}

    try:
        result = await scrape(link)
    except LoginRequired as exc:
        _log(record_id, link, "login_required", str(exc), {})
        return {"status": "login_required", "message": str(exc)}
    except Exception as exc:
        LOGGER.exception("scrape failed for %s", link)
        _log(record_id, link, "error", str(exc), {})
        return {"status": "error", "message": str(exc)}

    feishu.update_record(record_id, result.fields)
    payload = {
        "fields": result.fields,
        "missing": result.missing,
    }
    _log(record_id, link, "ok" if not result.missing else "partial", "", payload)
    return {"status": "ok", **payload}


def _log(record_id: str, link: str | None, status: str, message: str, payload: dict[str, Any]) -> None:
    try:
        supabase().table("scrape_log").insert(
            {
                "record_id": record_id,
                "url": link,
                "status": status,
                "message": message,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
    except Exception as exc:
        LOGGER.warning("write scrape_log failed: %s", exc)
