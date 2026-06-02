from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import auth, login_session
from app.config import get_settings
from app.runner import run_for_record, run_scan_all, scan_status, tail_log
from app.scraper import LoginRequired, scrape

LOGGER = logging.getLogger("uvicorn.error")
app = FastAPI(title="xiaoyuzhou-zhuiguang-sync")


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "has_state": auth.has_state()}


@app.post("/feishu/trigger")
async def feishu_trigger(
    request: Request,
    background: BackgroundTasks,
    x_trigger_secret: Optional[str] = Header(default=None, alias="X-Trigger-Secret"),
) -> dict:
    s = get_settings()
    if x_trigger_secret != s.feishu_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid secret")
    body = await request.json()
    if _is_scan_all_payload(body):
        background.add_task(_safe_scan_all)
        return {"accepted": True, "mode": "scan_all"}
    record_id = _extract_record_id(body)
    if not record_id:
        raise HTTPException(status_code=400, detail="missing record_id in payload")
    background.add_task(_safe_run, record_id)
    return {"accepted": True, "record_id": record_id}


@app.post("/feishu/trigger/sync")
async def feishu_trigger_sync(
    request: Request,
    x_trigger_secret: Optional[str] = Header(default=None, alias="X-Trigger-Secret"),
) -> dict:
    s = get_settings()
    if x_trigger_secret != s.feishu_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid secret")
    body = await request.json()
    record_id = _extract_record_id(body)
    if not record_id:
        raise HTTPException(status_code=400, detail="missing record_id in payload")
    return await run_for_record(record_id)


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(token: Optional[str] = Query(default=None)) -> HTMLResponse:
    _require_admin(token)
    s = get_settings()
    html = f"""
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <title>登录 zhuiguang.xyz</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, sans-serif; }}
    .bar {{ padding: 8px 12px; background: #111; color: #fff; display: flex; gap: 8px; align-items: center; }}
    .bar button {{ padding: 6px 10px; }}
    iframe {{ width: 100vw; height: calc(100vh - 44px); border: 0; }}
    code {{ background: #222; color: #6f6; padding: 2px 4px; }}
  </style>
</head>
<body>
  <div class="bar">
    <button onclick="start()">启动浏览器</button>
    <button onclick="stop()">关闭浏览器</button>
    <span id="status">就绪</span>
    <span style="margin-left:auto">登录成功后，状态会变为 <code>saved</code>，可直接关闭页面</span>
  </div>
  <iframe src="about:blank" id="vnc"></iframe>
  <script>
    const token = new URLSearchParams(location.search).get('token') || '';
    const VNC_URL = '/novnc/vnc_lite.html?autoconnect=1&resize=remote&path=websockify';
    async function start() {{
      document.getElementById('status').innerText = '正在启动虚拟桌面…';
      const r = await fetch('/admin/login/start?token=' + encodeURIComponent(token), {{ method: 'POST' }});
      document.getElementById('status').innerText = JSON.stringify(await r.json());
      // 桌面就绪后再连 noVNC，避免空闲时连接失败的报错
      document.getElementById('vnc').src = VNC_URL;
    }}
    async function stop() {{
      const r = await fetch('/admin/login/stop?token=' + encodeURIComponent(token), {{ method: 'POST' }});
      document.getElementById('status').innerText = JSON.stringify(await r.json());
      document.getElementById('vnc').src = 'about:blank';
    }}
    async function poll() {{
      try {{
        const r = await fetch('/admin/login/status?token=' + encodeURIComponent(token));
        const j = await r.json();
        document.getElementById('status').innerText = j.state + ' - ' + (j.message || '');
      }} catch (e) {{}}
      setTimeout(poll, 2000);
    }}
    poll();
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.post("/admin/login/start")
async def admin_login_start(token: Optional[str] = Query(default=None)) -> dict:
    _require_admin(token)
    return await login_session.start()


@app.post("/admin/login/stop")
async def admin_login_stop(token: Optional[str] = Query(default=None)) -> dict:
    _require_admin(token)
    return await login_session.stop()


@app.get("/admin/login/status")
async def admin_login_status(token: Optional[str] = Query(default=None)) -> dict:
    _require_admin(token)
    return login_session.get_status()


@app.post("/admin/upload-state")
async def admin_upload_state(
    token: Optional[str] = Query(default=None),
    file: UploadFile = File(...),
) -> dict:
    _require_admin(token)
    raw = await file.read()
    try:
        state = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}")
    auth.save_state(state)
    return {"ok": True}


@app.post("/admin/clear-state")
@app.get("/admin/clear-state")
async def admin_clear_state(token: Optional[str] = Query(default=None)) -> dict:
    _require_admin(token)
    auth.clear_state()
    return {"ok": True}


@app.get("/admin/debug")
async def admin_debug(
    token: Optional[str] = Query(default=None),
    url: str = Query(...),
    with_xhr: bool = Query(default=False),
    xhr_filter: Optional[str] = Query(default=None),
) -> dict:
    _require_admin(token)
    try:
        result = await scrape(url, debug=True)
    except LoginRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    out: dict = {
        "url": result.url,
        "fields": result.fields,
        "missing": result.missing,
        "api_data_found": result.api_data is not None,
        "page_text_preview": (result.page_text or "")[:2000],
        "xhr_count": len(result.raw_xhr),
        "xhr_urls": [x["url"] for x in result.raw_xhr][:50],
        "screenshot": result.screenshot_path,
    }
    if with_xhr:
        entries = result.raw_xhr
        if xhr_filter:
            entries = [x for x in entries if xhr_filter in x.get("url", "")]
        out["xhr_bodies"] = entries
    return out


@app.post("/admin/run")
@app.get("/admin/run")
async def admin_run(
    token: Optional[str] = Query(default=None),
    record_id: str = Query(...),
) -> dict:
    _require_admin(token)
    return await run_for_record(record_id)


@app.post("/admin/scan-all")
@app.get("/admin/scan-all")
async def admin_scan_all(
    background: BackgroundTasks,
    token: Optional[str] = Query(default=None),
    wait: bool = Query(default=False),
) -> dict:
    _require_admin(token)
    if wait:
        return await run_scan_all()
    background.add_task(_safe_scan_all)
    return {"accepted": True, **scan_status()}


@app.get("/admin/scan-status")
async def admin_scan_status(token: Optional[str] = Query(default=None)) -> dict:
    _require_admin(token)
    return scan_status()


@app.get("/admin/log")
async def admin_log(
    token: Optional[str] = Query(default=None),
    n: int = Query(default=100, ge=1, le=1000),
) -> dict:
    _require_admin(token)
    return {"entries": tail_log(n)}


def _require_admin(token: Optional[str]) -> None:
    s = get_settings()
    if token != s.admin_token:
        raise HTTPException(status_code=401, detail="invalid admin token")


_RECORD_ID_RE = re.compile(r"rec[a-zA-Z0-9]{6,}")


def _extract_record_id(payload: dict) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    raw: Optional[str] = None
    for key in ("record_id", "recordId", "id"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            raw = v
            break
    if raw is None:
        record = payload.get("record")
        if isinstance(record, dict):
            for key in ("record_id", "id"):
                v = record.get(key)
                if isinstance(v, str) and v:
                    raw = v
                    break
    if raw is None:
        return None
    # 兜底：飞书 Body 占位有残留时，从字符串里捞出 rec... 子串
    m = _RECORD_ID_RE.search(raw)
    if m:
        return m.group(0)
    return raw


def _is_scan_all_payload(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("scan_all", "scanAll", "all"):
        v = payload.get(key)
        if v in (True, "true", "True", 1, "1"):
            return True
    return False


async def _safe_run(record_id: str) -> None:
    try:
        await run_for_record(record_id)
    except Exception as exc:
        LOGGER.exception("background run failed for %s: %s", record_id, exc)


async def _safe_scan_all() -> None:
    try:
        await run_scan_all()
    except Exception as exc:
        LOGGER.exception("background scan_all failed: %s", exc)
