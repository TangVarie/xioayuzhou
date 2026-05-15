from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from playwright.async_api import async_playwright

from app.auth import load_state, save_state
from app.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)

VIEWPORT = {"width": 1440, "height": 900}
NAV_TIMEOUT_MS = 60000
TOP_N = 2  # 多选字段：取占比前 N 名

PID_RE = re.compile(r"/podcast/([0-9a-fA-F]+)")

AGE_LABELS = {
    "under_18": "<18",
    "between_18_and_22": "18-22",
    "between_23_and_28": "23-28",
    "between_29_and_35": "29-35",
    "between_36_and_40": "36-40",
    "over_40": ">40",
}

CITY_LABELS = {
    "first_level": "一线（含新一线）",
    "second_level": "二线及以下",
    "oversea": "海外",
}


@dataclass
class ScrapeResult:
    url: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw_xhr: list[dict[str, Any]] = field(default_factory=list)
    page_text: str = ""
    screenshot_path: Optional[str] = None
    missing: list[str] = field(default_factory=list)
    api_data: Optional[dict[str, Any]] = None


class LoginRequired(Exception):
    pass


async def scrape(url: str, *, debug: bool = False) -> ScrapeResult:
    state = load_state()
    if not state:
        raise LoginRequired("尚未保存 zhuiguang.xyz 登录态，请先在管理员页面完成登录")

    pid = _extract_pid(url)
    if not pid:
        raise ValueError(f"URL 里找不到 pid: {url}")

    settings = get_settings()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=state, viewport=VIEWPORT)
        page = await context.new_page()
        xhr: list[dict[str, Any]] = []

        async def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "application/json" not in ct:
                    return
                if resp.status >= 400:
                    return
                body = await resp.json()
                xhr.append({"url": resp.url, "status": resp.status, "body": body})
            except Exception:
                return

        page.on("response", on_response)

        await page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)

        if _looks_like_login_page(page.url):
            await browser.close()
            raise LoginRequired("zhuiguang.xyz 登录态已失效，请重新登录")

        # 给 response handler 一点时间完成（await body 是异步的）
        await asyncio.sleep(0.5)

        api_data = _find_podcast_data(xhr, pid)

        # 兜底：XHR 没捕获到就主动调一次
        if api_data is None:
            try:
                api_data = await page.evaluate(
                    """async (pid) => {
                        const r = await fetch('https://api.zhuiguang.xyz/v1/podcast/get?pid=' + pid, {credentials: 'include'});
                        if (!r.ok) return null;
                        const j = await r.json();
                        return j.data || null;
                    }""",
                    pid,
                )
            except Exception as exc:
                LOGGER.warning("fallback fetch podcast/get failed: %s", exc)

        result = ScrapeResult(url=url, raw_xhr=xhr, api_data=api_data)

        if api_data:
            result.fields = _extract_from_api(api_data, settings)

        # 给所有 spec 都补上 key（即使是 None / []），方便上层一致处理 missing
        for spec in settings.field_specs():
            result.fields.setdefault(spec.name, [] if spec.kind == "multi_select" else None)
        result.missing = [
            spec.name
            for spec in settings.field_specs()
            if result.fields.get(spec.name) in (None, "", [])
        ]

        if debug:
            shot = "/tmp/zhuiguang_debug.png"
            try:
                await page.screenshot(path=shot, full_page=True)
                result.screenshot_path = shot
            except Exception:
                pass
            try:
                result.page_text = await page.evaluate("() => document.body.innerText")
            except Exception:
                pass

        state_after = await context.storage_state()
        save_state(state_after)
        await browser.close()
        return result


def _extract_pid(url: str) -> Optional[str]:
    m = PID_RE.search(url)
    return m.group(1) if m else None


def _looks_like_login_page(current_url: str) -> bool:
    lowered = current_url.lower()
    return "login" in lowered or "signin" in lowered or "auth" in lowered


def _find_podcast_data(xhr: list[dict[str, Any]], pid: str) -> Optional[dict]:
    for entry in xhr:
        u = entry.get("url", "")
        if "/v1/podcast/get" in u and pid in u:
            body = entry.get("body") or {}
            data = body.get("data")
            if isinstance(data, dict):
                return data
    return None


def _extract_from_api(data: dict, settings: Settings) -> dict[str, Any]:
    out: dict[str, Any] = {}

    if (v := data.get("subscriptionCount")) is not None:
        out[settings.field_subscribers] = v
    if (v := data.get("avgPlayCount")) is not None:
        out[settings.field_avg_listen] = v
    if (v := data.get("avgDurationInSeconds")) is not None:
        out[settings.field_avg_duration] = round(float(v) / 60.0, 1)
    if (v := data.get("avgUserEpisodePlayedSeconds")) is not None:
        out[settings.field_avg_play] = round(float(v) / 60.0, 1)
    if (v := data.get("avgCommentCount")) is not None:
        out[settings.field_avg_comments] = v

    if isinstance(gd := data.get("genderDistribution"), dict):
        if (v := gd.get("female")) is not None:
            out[settings.field_female_ratio] = float(v)

    if isinstance(md := data.get("manufacturerDistribution"), dict):
        if (v := md.get("apple")) is not None:
            out[settings.field_iphone_ratio] = float(v)

    if isinstance(ad := data.get("ageDistribution"), dict):
        out[settings.field_age_distribution] = _top_labels(ad, AGE_LABELS)

    if isinstance(cd := data.get("cityDistribution"), dict):
        out[settings.field_location_distribution] = _top_labels(cd, CITY_LABELS)

    return out


def _top_labels(dist: dict, mapping: dict[str, str]) -> list[str]:
    pairs = sorted(
        ((k, float(v)) for k, v in dist.items() if isinstance(v, (int, float))),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return [mapping.get(k, k) for k, _ in pairs[:TOP_N]]
