from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from playwright.async_api import async_playwright

from app.auth import load_state, save_state
from app.config import FieldSpec, get_settings

LOGGER = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    url: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw_xhr: list[dict[str, Any]] = field(default_factory=list)
    page_text: str = ""
    screenshot_path: Optional[str] = None
    missing: list[str] = field(default_factory=list)


class LoginRequired(Exception):
    pass


async def scrape(url: str, *, debug: bool = False) -> ScrapeResult:
    s = get_settings()
    state = load_state()
    if not state:
        raise LoginRequired("尚未保存 zhuiguang.xyz 登录态，请先在管理员页面完成登录")

    specs = s.field_specs()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            storage_state=state,
            viewport={"width": s.screen_width, "height": s.screen_height},
        )
        page = await context.new_page()
        xhr: list[dict[str, Any]] = []
        page.on("response", lambda resp: _maybe_capture(resp, xhr))

        await page.goto(url, wait_until="networkidle", timeout=s.scrape_nav_timeout_ms)

        if _looks_like_login_page(page.url):
            await browser.close()
            raise LoginRequired("zhuiguang.xyz 登录态已失效，请重新登录")

        if s.scrape_ready_selector:
            try:
                await page.wait_for_selector(
                    s.scrape_ready_selector, timeout=s.scrape_ready_timeout_ms
                )
            except Exception:
                pass

        page_text = await page.evaluate("() => document.body.innerText")
        result = ScrapeResult(url=url, page_text=page_text, raw_xhr=xhr)
        result.fields = _extract_fields(page_text, xhr, specs)
        result.missing = [
            spec.name for spec in specs if result.fields.get(spec.name) in (None, "", [])
        ]

        if debug:
            shot = "/tmp/zhuiguang_debug.png"
            await page.screenshot(path=shot, full_page=True)
            result.screenshot_path = shot

        state_after = await context.storage_state()
        save_state(state_after)
        await browser.close()
        return result


def _looks_like_login_page(current_url: str) -> bool:
    lowered = current_url.lower()
    return "login" in lowered or "signin" in lowered or "auth" in lowered


def _maybe_capture(resp, sink: list[dict[str, Any]]) -> None:
    try:
        ct = (resp.headers or {}).get("content-type", "")
        if "application/json" not in ct:
            return
        if resp.status >= 400:
            return
        url = resp.url
    except Exception:
        return

    async def _read():
        try:
            body = await resp.json()
        except Exception:
            return
        sink.append({"url": url, "body": body})

    import asyncio

    asyncio.create_task(_read())


_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)*")
_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def _extract_fields(
    text: str, xhr: list[dict[str, Any]], specs: list[FieldSpec]
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    text_norm = _normalize_text(text)

    for spec in specs:
        if spec.kind == "progress":
            fields[spec.name] = _extract_percent(text_norm, spec.name)
        elif spec.kind == "multi_select":
            fields[spec.name] = _extract_multi(text_norm, xhr, spec.name)
        elif spec.kind == "duration":
            fields[spec.name] = _extract_number(text_norm, spec.name, is_duration=True)
        else:
            fields[spec.name] = _extract_number(text_norm, spec.name, is_duration=False)

    for spec in specs:
        if fields.get(spec.name) in (None, "", []):
            json_val = _search_xhr(xhr, spec.name)
            if json_val is not None:
                fields[spec.name] = json_val
    return fields


def _normalize_text(text: str) -> str:
    return text.replace("　", " ").replace(":", ":")


def _extract_number(text: str, label: str, *, is_duration: bool) -> Optional[float]:
    pattern = re.compile(rf"{re.escape(label)}\s*[:：]?\s*([^\n]*)")
    m = pattern.search(text)
    if not m:
        return None
    chunk = m.group(1).strip()
    if is_duration:
        return _parse_duration(chunk)
    return _first_number(chunk)


def _extract_percent(text: str, label: str) -> Optional[float]:
    pattern = re.compile(rf"{re.escape(label)}\s*[:：]?\s*([^\n]*)")
    m = pattern.search(text)
    if not m:
        return None
    chunk = m.group(1).strip()
    pm = _PERCENT_RE.search(chunk)
    if pm:
        return float(pm.group(1)) / 100.0
    num = _first_number(chunk)
    if num is None:
        return None
    return num if num <= 1 else num / 100.0


def _extract_multi(text: str, xhr: list[dict[str, Any]], label: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(label)}\s*[:：]?\s*([^\n]+)")
    m = pattern.search(text)
    candidates: list[str] = []
    if m:
        chunk = m.group(1).strip()
        parts = re.split(r"[、,，；;|/\s]+", chunk)
        candidates.extend([p for p in parts if p and not p.isdigit() and "%" not in p])
    if not candidates:
        json_val = _search_xhr(xhr, label)
        if isinstance(json_val, list):
            candidates = [str(v) for v in json_val]
        elif isinstance(json_val, str):
            candidates = [v.strip() for v in re.split(r"[、,，;|/\s]+", json_val) if v.strip()]
    seen = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _first_number(chunk: str) -> Optional[float]:
    m = _NUMBER_RE.search(chunk)
    if not m:
        return None
    s = m.group(0).replace(",", "")
    try:
        f = float(s)
    except ValueError:
        return None
    chunk_lower = chunk.lower()
    if "万" in chunk:
        f *= 10000
    elif "亿" in chunk:
        f *= 100000000
    elif "k" in chunk_lower and "%" not in chunk:
        f *= 1000
    return f


_DURATION_RE = re.compile(
    r"(?:(\d+)\s*小时)?\s*(?:(\d+)\s*分(?:钟)?)?\s*(?:(\d+)\s*秒)?"
)


def _parse_duration(chunk: str) -> Optional[float]:
    chunk = chunk.strip()
    if not chunk:
        return None
    m = _DURATION_RE.search(chunk)
    if m and any(m.groups()):
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        total = h * 3600 + mi * 60 + s
        if total > 0:
            return total / 60.0
    if ":" in chunk:
        parts = chunk.split(":")[:3]
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            nums = []
        if nums:
            while len(nums) < 3:
                nums.insert(0, 0)
            h, mi, s = nums
            return (h * 3600 + mi * 60 + s) / 60.0
    return _first_number(chunk)


def _search_xhr(xhr: list[dict[str, Any]], label: str) -> Any:
    for entry in xhr:
        found = _walk(entry.get("body"), label)
        if found is not None:
            return found
    return None


def _walk(node: Any, label: str) -> Any:
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and label in k:
                return v
            found = _walk(v, label)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _walk(item, label)
            if found is not None:
                return found
    return None
