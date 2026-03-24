#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

import crawler


def walk_keys(node: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{prefix}.{k}" if prefix else k
            yield p
            yield from walk_keys(v, p)
    elif isinstance(node, list):
        for i, item in enumerate(node[:3]):
            p = f"{prefix}[]"
            yield p
            yield from walk_keys(item, p)


def write_field_csv(path: Path, counter: Counter) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["field_path", "hit_count"])
        for key, cnt in counter.most_common():
            w.writerow([key, cnt])


def run(args: argparse.Namespace) -> Path:
    token_from_file, cookie_from_file = crawler.load_auth(args.auth_file)
    cfg = crawler.CrawlConfig(
        token=args.token or token_from_file or "",
        cookie=args.cookie or cookie_from_file or "",
        timeout=args.timeout,
        retries=args.retries,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
    )
    pids = crawler.load_channel_ids(Path(args.channels))

    c = Counter()

    for pid in pids[: args.max_channels]:
        try:
            pd = crawler.fetch_podcast(pid, cfg)
            for k in walk_keys(pd):
                c[k] += 1
        except Exception:
            continue

        try:
            episodes = crawler.fetch_episodes(pid, cfg, max_episodes=args.max_episodes)
            for e in episodes:
                for k in walk_keys(e):
                    c[f"episode.{k}"] += 1
        except Exception:
            continue

    out = Path(args.out)
    write_field_csv(out, c)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="字段勘探：统计接口响应字段路径")
    p.add_argument("--channels", required=True)
    p.add_argument("--out", default="out/field_discovery.csv")
    p.add_argument("--auth-file", default="", help="登录凭据 JSON 文件路径（由 login_bridge.py 生成）")
    p.add_argument("--token", default="")
    p.add_argument("--cookie", default="")
    p.add_argument("--max-channels", type=int, default=20)
    p.add_argument("--max-episodes", type=int, default=20)
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--retries", type=int, default=1)
    p.add_argument("--sleep-min", type=float, default=0.1)
    p.add_argument("--sleep-max", type=float, default=0.5)
    args = p.parse_args()
    print(run(args))
