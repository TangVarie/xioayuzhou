#!/usr/bin/env python3
"""
一键封装入口：本地网络执行
- 可选先登录（保存 auth.json）
- 再执行抓取
- 可选执行字段勘探
"""

import argparse
import json
import webbrowser
from pathlib import Path

import crawler
import discover

LOGIN_URL = "https://www.xiaoyuzhoufm.com"


def ensure_auth(auth_file: Path, do_login: bool) -> None:
    if auth_file.exists():
        return
    if not do_login:
        raise SystemExit(f"auth 文件不存在：{auth_file}。请加 --login 或手动创建。")

    print("=" * 60)
    print("即将打开小宇宙官网，请先登录。")
    print(f"URL: {LOGIN_URL}")
    print("登录后请把 x-jike-access-token / Cookie 粘贴回来。")
    print("=" * 60)
    try:
        webbrowser.open(LOGIN_URL)
    except Exception:
        print("[提示] 无法自动打开浏览器，请手动打开 URL。")

    token = input("x-jike-access-token（可空）: ").strip()
    cookie = input("Cookie（可空）: ").strip()
    if not token and not cookie:
        raise SystemExit("未输入 token/cookie，取消。")

    auth_file.write_text(
        json.dumps({"x_jike_access_token": token, "cookie": cookie}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已写入 {auth_file}")


def run_crawl(args: argparse.Namespace) -> None:
    ns = argparse.Namespace(
        channels=args.channels,
        out_dir=args.out_dir,
        auth_file=str(args.auth_file),
        token="",
        cookie="",
        max_episodes=args.max_episodes,
        timeout=args.timeout,
        retries=args.retries,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
    )
    ch, ep, rp = crawler.run(ns)
    print("抓取完成：")
    print(f"- {ch}")
    print(f"- {ep}")
    print(f"- {rp}")


def run_discovery(args: argparse.Namespace) -> None:
    ns = argparse.Namespace(
        channels=args.channels,
        out=str(Path(args.out_dir) / "field_discovery.csv"),
        auth_file=str(args.auth_file),
        token="",
        cookie="",
        max_channels=args.discovery_channels,
        max_episodes=args.discovery_episodes,
        timeout=args.timeout,
        retries=max(1, args.retries),
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
    )
    out = discover.run(ns)
    print(f"字段勘探完成：{out}")


def main() -> None:
    p = argparse.ArgumentParser(description="小宇宙本地一键执行器")
    p.add_argument("--channels", default="channels.txt", help="频道列表文件")
    p.add_argument("--auth-file", default="auth.json", help="登录凭据文件")
    p.add_argument("--out-dir", default="out", help="输出目录")
    p.add_argument("--login", action="store_true", help="若无 auth 文件则引导官网登录")
    p.add_argument("--discover", action="store_true", help="抓取完成后顺便跑字段勘探")
    p.add_argument("--max-episodes", type=int, default=50, help="每个频道抓取单集上限")
    p.add_argument("--discovery-channels", type=int, default=20, help="字段勘探使用的频道数")
    p.add_argument("--discovery-episodes", type=int, default=20, help="字段勘探每频道单集数")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--sleep-min", type=float, default=0.2)
    p.add_argument("--sleep-max", type=float, default=0.8)
    args = p.parse_args()

    auth_file = Path(args.auth_file)
    ensure_auth(auth_file, args.login)
    run_crawl(args)
    if args.discover:
        run_discovery(args)


if __name__ == "__main__":
    main()
