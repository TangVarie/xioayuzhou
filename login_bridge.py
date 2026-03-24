#!/usr/bin/env python3
"""
登录桥接脚本：
1) 打开小宇宙官网登录页
2) 提示用户登录后从浏览器复制 token/cookie
3) 保存到 auth.json，供 crawler.py / discover.py 读取
"""

import argparse
import json
import webbrowser
from pathlib import Path

LOGIN_URL = "https://www.xiaoyuzhoufm.com"


def main() -> None:
    parser = argparse.ArgumentParser(description="小宇宙官网登录桥接")
    parser.add_argument("--out", default="auth.json", help="输出凭据文件路径")
    args = parser.parse_args()

    print("=" * 60)
    print("1) 即将为你打开小宇宙官网，请先在网页完成登录。")
    print(f"   URL: {LOGIN_URL}")
    print("2) 登录后，在浏览器开发者工具中拿到以下信息：")
    print("   - x-jike-access-token（优先）")
    print("   - Cookie（可选，建议一并保存）")
    print("=" * 60)

    try:
        ok = webbrowser.open(LOGIN_URL)
        if not ok:
            print("[提示] 未能自动拉起浏览器，请手动打开上面的 URL。")
    except Exception:
        print("[提示] 当前环境无法自动打开浏览器，请手动打开上面的 URL。")

    token = input("请输入 x-jike-access-token（可留空）: ").strip()
    cookie = input("请输入 Cookie（可留空）: ").strip()

    if not token and not cookie:
        raise SystemExit("未提供 token/cookie，已取消保存。")

    payload = {
        "x_jike_access_token": token,
        "cookie": cookie,
    }

    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已保存登录凭据: {out}")
    print("下一步可运行：")
    print("  python crawler.py --channels channels.txt --auth-file auth.json --out-dir out")


if __name__ == "__main__":
    main()
