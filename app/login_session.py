from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.auth import save_state
from app.config import get_settings

LOGGER = logging.getLogger(__name__)


@dataclass
class LoginSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    task: asyncio.Task

    async def stop(self) -> None:
        if not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await self.context.close()
        except Exception:
            pass
        try:
            await self.browser.close()
        except Exception:
            pass
        try:
            await self.playwright.stop()
        except Exception:
            pass


_current: Optional[LoginSession] = None
_lock = asyncio.Lock()
_status: dict = {"state": "idle", "message": "未启动"}


def get_status() -> dict:
    return dict(_status)


async def start() -> dict:
    global _current
    async with _lock:
        if _current is not None and not _current.task.done():
            return {"state": _status.get("state"), "message": "登录会话已在进行中"}

        s = get_settings()
        success_hints = s.login_success_hints_list()
        cookie_hints = s.session_cookie_hints_list()

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--start-maximized",
                f"--display={s.display}",
            ],
            env={"DISPLAY": s.display},
        )
        context = await browser.new_context(viewport=None)
        page = await context.new_page()
        await page.goto(s.zhuiguang_login_url, wait_until="domcontentloaded")

        _status.update(
            {"state": "waiting", "message": f"请在 noVNC 窗口里登录 {s.zhuiguang_login_url}"}
        )

        async def _watcher():
            try:
                while True:
                    await asyncio.sleep(2.0)
                    try:
                        url = page.url
                    except Exception:
                        url = ""
                    if success_hints and any(hint in url for hint in success_hints):
                        cookies = await context.cookies()
                        if any(_looks_like_session(c, cookie_hints) for c in cookies):
                            state = await context.storage_state()
                            save_state(state)
                            _status.update(
                                {"state": "saved", "message": "登录态已保存到 Volume"}
                            )
                            break
            except asyncio.CancelledError:
                _status.update({"state": "cancelled", "message": "登录会话已取消"})
                raise
            except Exception as exc:
                LOGGER.exception("login watcher failed: %s", exc)
                _status.update({"state": "error", "message": f"监听失败: {exc}"})

        task = asyncio.create_task(_watcher())
        _current = LoginSession(playwright=pw, browser=browser, context=context, task=task)
        return {"state": _status.get("state"), "message": _status.get("message")}


async def stop() -> dict:
    global _current
    async with _lock:
        if _current is None:
            return {"state": "idle", "message": "无活动会话"}
        sess = _current
        _current = None
        await sess.stop()
        if _status.get("state") == "waiting":
            _status.update({"state": "stopped", "message": "已停止"})
        return {"state": _status.get("state"), "message": _status.get("message")}


def _looks_like_session(cookie: dict, hints: list[str]) -> bool:
    if not hints:
        return True
    name = (cookie.get("name") or "").lower()
    return any(h in name for h in hints)
