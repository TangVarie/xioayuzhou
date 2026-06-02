from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from playwright.async_api import async_playwright

from app.auth import save_state
from app.config import get_settings

LOGGER = logging.getLogger(__name__)

LOGIN_URL = "https://zhuiguang.xyz/"
SUCCESS_URL_HINTS = ("/advertiser", "/dashboard", "/home")
SESSION_COOKIE_HINTS = ("session", "token", "auth", "sid", "passport", "user")

# 这几个进程组成 noVNC 用的虚拟桌面，只在登录时按需启动，登录完/超时就关，
# 平时不占内存。见 supervisord.conf 里它们的 autostart=false。
SUPERVISOR_CONF = "/etc/supervisor/conf.d/app.conf"
X_STACK = ["xvfb", "fluxbox", "x11vnc", "websockify"]
IDLE_TIMEOUT_SECONDS = 600  # 启动后 10 分钟没登录成功就自动关掉桌面


@dataclass
class LoginSession:
    task: asyncio.Task
    teardown: Callable[[], Awaitable[None]]

    async def stop(self) -> None:
        if not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        await self.teardown()


_current: Optional[LoginSession] = None
_lock = asyncio.Lock()
_status: dict = {"state": "idle", "message": "未启动"}


def get_status() -> dict:
    return dict(_status)


def _have_supervisor() -> bool:
    return shutil.which("supervisorctl") is not None and Path(SUPERVISOR_CONF).exists()


def _supervisorctl(action: str, programs: list[str]) -> None:
    try:
        subprocess.run(
            ["supervisorctl", "-c", SUPERVISOR_CONF, action, *programs],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except FileNotFoundError:
        pass  # 本地开发没有 supervisor，直接忽略
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("supervisorctl %s %s failed: %s", action, programs, exc)


async def _wait_for_display(display: str, timeout: float = 15.0) -> bool:
    # display ":99" -> socket /tmp/.X11-unix/X99
    num = display.lstrip(":").split(".")[0]
    sock = Path(f"/tmp/.X11-unix/X{num}")
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if sock.exists():
            return True
        await asyncio.sleep(0.3)
    return sock.exists()


async def _start_x_stack(display: str) -> bool:
    """按需拉起虚拟桌面。返回 False 表示启动失败。本地无 supervisor 时直接放行。"""
    if not _have_supervisor():
        return True
    await asyncio.to_thread(_supervisorctl, "start", ["xvfb"])
    if not await _wait_for_display(display):
        await asyncio.to_thread(_supervisorctl, "stop", X_STACK)
        return False
    await asyncio.to_thread(_supervisorctl, "start", ["fluxbox", "x11vnc", "websockify"])
    await asyncio.sleep(1.0)  # 给 x11vnc/websockify 一点时间监听端口
    return True


async def _stop_x_stack() -> None:
    if _have_supervisor():
        await asyncio.to_thread(_supervisorctl, "stop", X_STACK)


async def start() -> dict:
    global _current
    async with _lock:
        if _current is not None and not _current.task.done():
            return {"state": _status.get("state"), "message": "登录会话已在进行中"}

        s = get_settings()

        _status.update({"state": "starting", "message": "正在启动虚拟桌面…"})
        if not await _start_x_stack(s.display):
            _status.update({"state": "error", "message": "虚拟桌面启动失败，请重试"})
            return dict(_status)

        try:
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
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        except Exception as exc:
            LOGGER.exception("launch headed browser failed: %s", exc)
            await _stop_x_stack()
            _status.update({"state": "error", "message": f"浏览器启动失败: {exc}"})
            return dict(_status)

        _status.update({"state": "waiting", "message": "请在 noVNC 窗口里登录 zhuiguang.xyz"})

        _torn = {"done": False}
        _teardown_lock = asyncio.Lock()

        async def _teardown() -> None:
            async with _teardown_lock:
                if _torn["done"]:
                    return
                _torn["done"] = True
                for closer in (context.close, browser.close, pw.stop):
                    try:
                        await closer()
                    except Exception:
                        pass
                await _stop_x_stack()

        async def _watcher() -> None:
            loop = asyncio.get_event_loop()
            deadline = loop.time() + IDLE_TIMEOUT_SECONDS
            try:
                while loop.time() < deadline:
                    await asyncio.sleep(2.0)
                    try:
                        url = page.url
                    except Exception:
                        url = ""
                    if any(hint in url for hint in SUCCESS_URL_HINTS):
                        cookies = await context.cookies()
                        if any(_looks_like_session(c) for c in cookies):
                            state = await context.storage_state()
                            save_state(state)
                            _status.update({"state": "saved", "message": "登录态已保存，桌面已释放"})
                            await asyncio.sleep(1.5)  # 让前端轮询到 saved 再关
                            await _teardown()
                            return
                _status.update({"state": "timeout", "message": "登录超时，已自动关闭桌面"})
            except asyncio.CancelledError:
                _status.update({"state": "cancelled", "message": "登录会话已取消"})
                raise  # teardown 交给外部 stop()
            except Exception as exc:
                LOGGER.exception("login watcher failed: %s", exc)
                _status.update({"state": "error", "message": f"监听失败: {exc}"})
            await _teardown()

        task = asyncio.create_task(_watcher())
        _current = LoginSession(task=task, teardown=_teardown)
        return dict(_status)


async def stop() -> dict:
    global _current
    async with _lock:
        if _current is None:
            await _stop_x_stack()
            return {"state": "idle", "message": "无活动会话"}
        sess = _current
        _current = None
        await sess.stop()
        if _status.get("state") == "waiting":
            _status.update({"state": "stopped", "message": "已停止"})
        return dict(_status)


def _looks_like_session(cookie: dict) -> bool:
    name = (cookie.get("name") or "").lower()
    return any(h in name for h in SESSION_COOKIE_HINTS)
