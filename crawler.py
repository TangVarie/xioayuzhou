#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE_URL = "https://api.xiaoyuzhoufm.com"
UA = "Xiaoyuzhou/2.57.1 (build:1576; iOS 17.4.1)"


@dataclass
class CrawlConfig:
    token: str
    cookie: str
    timeout: int
    retries: int
    sleep_min: float
    sleep_max: float


def parse_pid(line: str) -> Optional[str]:
    s = line.strip()
    if not s:
        return None
    if re.fullmatch(r"[0-9a-f]{24}", s):
        return s
    m = re.search(r"/podcast/([0-9a-f]{24})", s)
    if m:
        return m.group(1)
    return None


def load_channel_ids(path: Path) -> List[str]:
    pids = []
    seen = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        pid = parse_pid(raw)
        if pid and pid not in seen:
            seen.add(pid)
            pids.append(pid)
    return pids


def _headers(token: str = "", extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    h = {
        "Host": "api.xiaoyuzhoufm.com",
        "User-Agent": UA,
        "Market": "AppStore",
        "App-BuildNo": "1576",
        "OS": "ios",
        "x-jike-access-token": token,
        "Manufacturer": "Apple",
        "BundleID": "app.podcast.cosmos",
        "Connection": "keep-alive",
        "Accept-Language": "zh-Hans-CN;q=0.9",
        "Model": "iPhone14,2",
        "app-permissions": "4",
        "Accept": "*/*",
        "App-Version": "2.57.1",
        "WifiConnected": "true",
        "OS-Version": "17.4.1",
        "x-custom-xiaoyuzhou-app-dev": "",
        "Local-Time": now,
        "Timezone": "Asia/Shanghai",
    }
    if extra:
        h.update(extra)
    return h


def load_auth(auth_file: str = "") -> Tuple[str, str]:
    if not auth_file:
        return "", ""
    path = Path(auth_file)
    if not path.exists():
        raise FileNotFoundError(f"auth file not found: {auth_file}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    token = str(payload.get("x_jike_access_token") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()
    return token, cookie


def request_json(
    method: str,
    url: str,
    cfg: CrawlConfig,
    payload: Optional[dict] = None,
) -> dict:
    data = None
    headers = _headers(cfg.token)
    if cfg.cookie:
        headers["Cookie"] = cfg.cookie
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)

    last_err = None
    for i in range(cfg.retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if i < cfg.retries:
                time.sleep((2 ** i) * 0.5)
            else:
                raise RuntimeError(f"request failed: {method} {url} -> {e}") from e
        finally:
            time.sleep(random.uniform(cfg.sleep_min, cfg.sleep_max))
    raise RuntimeError(str(last_err))


def fetch_podcast(pid: str, cfg: CrawlConfig) -> dict:
    url = f"{BASE_URL}/v1/podcast/get?pid={urllib.parse.quote(pid)}"
    return request_json("GET", url, cfg)


def fetch_episodes(pid: str, cfg: CrawlConfig, max_episodes: int = 50, order: str = "desc") -> List[dict]:
    episodes: List[dict] = []
    load_more_key = None
    while len(episodes) < max_episodes:
        payload: Dict[str, Any] = {"pid": pid, "order": order, "limit": "20"}
        if load_more_key:
            payload["loadMoreKey"] = load_more_key

        data = request_json("POST", f"{BASE_URL}/v1/episode/list", cfg, payload)
        items = (data.get("data") or {}).get("episodes") or []
        if not items:
            break

        episodes.extend(items)

        lmk = (data.get("data") or {}).get("loadMoreKey")
        if not lmk:
            break
        load_more_key = lmk

    return episodes[:max_episodes]


def extract_channel_row(pid: str, podcast_resp: dict) -> dict:
    p = (podcast_resp.get("data") or {}).get("podcast") or {}
    return {
        "pid": pid,
        "title": p.get("title") or p.get("name"),
        "author": p.get("author") or p.get("podcasters", [{}])[0].get("nickname"),
        "description": p.get("description"),
        "language": p.get("language"),
        "category": p.get("category"),
        "episode_count": p.get("episodeCount"),
        "subscriber_count": p.get("subscriberCount"),
        "play_count": p.get("playCount"),
        "comment_count": p.get("commentCount"),
        "last_update": p.get("latestEpisodePubDate") or p.get("updatedAt"),
    }


def extract_episode_rows(pid: str, episodes: Iterable[dict]) -> List[dict]:
    out = []
    for e in episodes:
        out.append(
            {
                "pid": pid,
                "eid": e.get("eid") or e.get("id"),
                "episode_title": e.get("title"),
                "pub_date": e.get("pubDate") or e.get("publishedAt"),
                "duration": e.get("duration"),
                "comment_count": e.get("commentCount"),
                "play_count": e.get("playCount"),
                "shownotes": e.get("shownotes") or e.get("description"),
            }
        )
    return out


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> Tuple[Path, Path, Path]:
    token_from_file, cookie_from_file = load_auth(args.auth_file)
    cfg = CrawlConfig(
        token=args.token or token_from_file or "",
        cookie=args.cookie or cookie_from_file or "",
        timeout=args.timeout,
        retries=args.retries,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
    )

    pids = load_channel_ids(Path(args.channels))
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)

    channel_rows: List[dict] = []
    episode_rows: List[dict] = []
    report_rows: List[dict] = []

    for pid in pids:
        started = time.time()
        try:
            podcast_resp = fetch_podcast(pid, cfg)
            eps = fetch_episodes(pid, cfg, max_episodes=args.max_episodes)
            channel_rows.append(extract_channel_row(pid, podcast_resp))
            episode_rows.extend(extract_episode_rows(pid, eps))
            report_rows.append(
                {
                    "pid": pid,
                    "status": "ok",
                    "episode_rows": len(eps),
                    "elapsed_sec": round(time.time() - started, 3),
                    "error": "",
                }
            )
        except Exception as e:
            report_rows.append(
                {
                    "pid": pid,
                    "status": "fail",
                    "episode_rows": 0,
                    "elapsed_sec": round(time.time() - started, 3),
                    "error": str(e),
                }
            )

    channels_csv = out_dir / f"channels_snapshot_{ts}.csv"
    episodes_csv = out_dir / f"episodes_snapshot_{ts}.csv"
    report_csv = out_dir / f"crawl_report_{ts}.csv"

    write_csv(channels_csv, channel_rows)
    write_csv(episodes_csv, episode_rows)
    write_csv(report_csv, report_rows)

    return channels_csv, episodes_csv, report_csv


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="小宇宙频道轻量采集器")
    p.add_argument("--channels", required=True, help="频道列表文件（每行 pid 或 URL）")
    p.add_argument("--out-dir", default="out", help="输出目录")
    p.add_argument("--auth-file", default="", help="登录凭据 JSON 文件路径（由 login_bridge.py 生成）")
    p.add_argument("--token", default="", help="x-jike-access-token（可选）")
    p.add_argument("--cookie", default="", help="Cookie（可选，常用于网页登录态）")
    p.add_argument("--max-episodes", type=int, default=50, help="每个频道最多抓取单集数")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--sleep-min", type=float, default=0.2)
    p.add_argument("--sleep-max", type=float, default=0.8)
    return p


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    channels_csv, episodes_csv, report_csv = run(args)
    print(channels_csv)
    print(episodes_csv)
    print(report_csv)
