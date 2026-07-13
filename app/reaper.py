"""Kill orphaned headless Chromium processes.

Why this exists: a scrape launches a headless Chromium. On the happy path it's
closed explicitly; on error the Playwright driver *should* reap it, but under
abnormal termination (OOM kill, container signal, a wedged page.goto) the
browser can be re-parented to PID 1 and keep spinning a JS render loop at ~1
vCPU forever — which is exactly the kind of leak that quietly runs up a cloud
bill for a month. supervisord only manages its own configured programs, so
nobody reaps that grandchild. This module is the backstop.

Safety by construction:
  * We ONLY ever match processes whose argv contains ``--headless``. The headed
    login browser (app/login_session.py launches Chromium with no --headless)
    is therefore *never* a candidate — verified by unit test.
  * The periodic caller only sweeps processes older than a threshold well above
    the scrape hard-timeout, so a live scrape can never be hit.
  * Pure standard library; on a host without ``/proc`` (local macOS dev) every
    function is a no-op, so it never interferes with local development.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Iterator

LOGGER = logging.getLogger(__name__)

_PROC = Path("/proc")
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

# argv must look like a browser AND be headless. Matching argv (not just comm)
# avoids ever touching the node driver, x11vnc, Xvfb, etc.
_BROWSER_MARKERS = ("chrome", "chromium", "headless_shell")


def _supported() -> bool:
    return _PROC.is_dir()


def _uptime_seconds() -> float:
    with (_PROC / "uptime").open() as f:
        return float(f.read().split()[0])


def _proc_start_seconds(pid: int, uptime: float) -> float | None:
    """Age of a pid in seconds, or None if it can't be read."""
    try:
        stat = (_PROC / str(pid) / "stat").read_text()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    # comm (field 2) is parenthesised and may contain spaces/parens — split on
    # the LAST ')' so the numeric fields after it parse cleanly.
    rparen = stat.rfind(")")
    if rparen == -1:
        return None
    rest = stat[rparen + 2 :].split()
    # After comm, tokens are field 3.. ; starttime is field 22 -> index 19.
    if len(rest) < 20:
        return None
    try:
        starttime_ticks = float(rest[19])
    except ValueError:
        return None
    age = uptime - (starttime_ticks / _CLK_TCK)
    return age if age >= 0 else 0.0


def _cmdline(pid: int) -> str:
    try:
        raw = (_PROC / str(pid) / "cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace")


def is_headless_chromium(cmdline: str) -> bool:
    """True only for a headless browser process. The headed login browser
    (no --headless flag) returns False. Kept pure + public for unit testing."""
    if "--headless" not in cmdline:
        return False
    lowered = cmdline.lower()
    return any(marker in lowered for marker in _BROWSER_MARKERS)


def _iter_pids() -> Iterator[int]:
    for entry in _PROC.iterdir():
        name = entry.name
        if name.isdigit():
            yield int(name)


def find_headless_chromium(min_age_seconds: float = 0.0) -> list[tuple[int, float]]:
    """Return (pid, age_seconds) for every headless Chromium older than the
    threshold. Empty on unsupported hosts."""
    if not _supported():
        return []
    try:
        uptime = _uptime_seconds()
    except (OSError, ValueError):
        return []
    self_pid = os.getpid()
    out: list[tuple[int, float]] = []
    for pid in _iter_pids():
        if pid in (self_pid, 1):
            continue
        if not is_headless_chromium(_cmdline(pid)):
            continue
        age = _proc_start_seconds(pid, uptime)
        if age is None or age < min_age_seconds:
            continue
        out.append((pid, age))
    return out


def sweep(min_age_seconds: float = 0.0) -> list[int]:
    """SIGTERM (then SIGKILL) every headless Chromium older than the threshold.
    Returns the pids it acted on."""
    victims = find_headless_chromium(min_age_seconds)
    killed: list[int] = []
    for pid, age in victims:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
            LOGGER.warning("reaped orphan headless chromium pid=%s age=%.0fs (SIGTERM)", pid, age)
        except ProcessLookupError:
            continue
        except PermissionError:
            LOGGER.warning("cannot signal pid=%s (permission)", pid)
            continue
    if killed:
        time.sleep(2.0)
        for pid in killed:
            try:
                os.kill(pid, 0)  # still alive?
                os.kill(pid, signal.SIGKILL)
                LOGGER.warning("orphan pid=%s survived SIGTERM, sent SIGKILL", pid)
            except (ProcessLookupError, PermissionError):
                pass
    return killed


def startup_sweep() -> list[int]:
    """At container boot nothing legitimate is running yet, so any headless
    Chromium present is a leftover from a previous life — kill them all."""
    if not _supported():
        return []
    killed = sweep(min_age_seconds=0.0)
    if killed:
        LOGGER.warning("startup_sweep killed leftover headless chromium: %s", killed)
    return killed
