"""The reaper must kill headless scrape browsers and NEVER the headed login
browser (or any system process). These are the cases that make it safe."""

from app.reaper import find_headless_chromium, is_headless_chromium

HEADLESS = [
    "/ms-playwright/chromium-1148/chrome-linux/chrome --headless --no-sandbox --remote-debugging-pipe",
    "/root/.cache/ms-playwright/chromium/chrome-linux/headless_shell --headless=new --disable-gpu",
    "/opt/chromium --headless --no-sandbox about:blank",
]

# The headed login browser (launched in app/login_session.py) has NO --headless
# flag; everything else here is a normal container process.
MUST_SPARE = [
    "/ms-playwright/chromium-1148/chrome-linux/chrome --no-sandbox --disable-dev-shm-usage --start-maximized --display=:99",
    "/usr/bin/Xvfb :99 -screen 0 1440x900x24 -ac +extension RANDR",
    "/usr/bin/x11vnc -display :99 -nopw -listen localhost -rfbport 5900",
    "/usr/bin/fluxbox",
    "/usr/local/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000",
    "node /ms-playwright/driver/package/lib/server",
    "/usr/sbin/nginx -g daemon off;",
    "websockify --web=/usr/share/novnc 6080 localhost:5900",
    "",
]


def test_matches_headless():
    for c in HEADLESS:
        assert is_headless_chromium(c), c


def test_spares_headed_login_browser_and_system():
    for c in MUST_SPARE:
        assert not is_headless_chromium(c), c


def test_find_does_not_crash_on_real_proc():
    # On Linux this walks /proc; on macOS it returns []. Either way, no crash.
    result = find_headless_chromium(min_age_seconds=1.0)
    assert isinstance(result, list)


if __name__ == "__main__":
    test_matches_headless()
    test_spares_headed_login_browser_and_system()
    test_find_does_not_crash_on_real_proc()
    print("all reaper tests passed")
