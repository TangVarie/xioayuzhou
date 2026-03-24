#!/usr/bin/env python3
"""
小宇宙轻量本地 GUI（零命令行）
- 打开官网登录
- 保存 auth.json
- 选择 channels.txt / 输出目录
- 点击按钮执行抓取与字段勘探
"""

import json
import queue
import threading
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import crawler
import discover

LOGIN_URL = "https://www.xiaoyuzhoufm.com"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("小宇宙数据采集器（轻量本地版）")
        self.geometry("860x680")

        self.channels_var = tk.StringVar(value=str(Path("channels.txt").resolve()))
        self.auth_var = tk.StringVar(value=str(Path("auth.json").resolve()))
        self.out_var = tk.StringVar(value=str(Path("out").resolve()))

        self.max_episodes_var = tk.IntVar(value=50)
        self.discovery_channels_var = tk.IntVar(value=20)
        self.discovery_episodes_var = tk.IntVar(value=20)
        self.timeout_var = tk.IntVar(value=20)
        self.retries_var = tk.IntVar(value=2)
        self.sleep_min_var = tk.DoubleVar(value=0.2)
        self.sleep_max_var = tk.DoubleVar(value=0.8)

        self.run_discover_var = tk.BooleanVar(value=True)

        self.token_var = tk.StringVar()
        self.cookie_var = tk.StringVar()

        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self.after(120, self._drain_logs)

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 6}

        frm_paths = ttk.LabelFrame(self, text="1) 文件路径")
        frm_paths.pack(fill="x", padx=10, pady=8)

        ttk.Label(frm_paths, text="频道文件 channels.txt").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm_paths, textvariable=self.channels_var, width=80).grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(frm_paths, text="选择...", command=self.pick_channels).grid(row=0, column=2, **pad)

        ttk.Label(frm_paths, text="登录凭据 auth.json").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm_paths, textvariable=self.auth_var, width=80).grid(row=1, column=1, sticky="we", **pad)
        ttk.Button(frm_paths, text="选择...", command=self.pick_auth).grid(row=1, column=2, **pad)

        ttk.Label(frm_paths, text="输出目录 out/").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm_paths, textvariable=self.out_var, width=80).grid(row=2, column=1, sticky="we", **pad)
        ttk.Button(frm_paths, text="选择...", command=self.pick_out_dir).grid(row=2, column=2, **pad)
        frm_paths.columnconfigure(1, weight=1)

        frm_auth = ttk.LabelFrame(self, text="2) 登录信息（可选）")
        frm_auth.pack(fill="x", padx=10, pady=8)

        ttk.Button(frm_auth, text="打开小宇宙官网登录", command=self.open_login).grid(row=0, column=0, sticky="w", **pad)

        ttk.Label(frm_auth, text="x-jike-access-token").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm_auth, textvariable=self.token_var, width=90).grid(row=1, column=1, columnspan=2, sticky="we", **pad)

        ttk.Label(frm_auth, text="Cookie").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm_auth, textvariable=self.cookie_var, width=90).grid(row=2, column=1, columnspan=2, sticky="we", **pad)

        ttk.Button(frm_auth, text="保存到 auth.json", command=self.save_auth).grid(row=3, column=0, sticky="w", **pad)
        ttk.Button(frm_auth, text="从 auth.json 加载", command=self.load_auth).grid(row=3, column=1, sticky="w", **pad)
        frm_auth.columnconfigure(1, weight=1)

        frm_opts = ttk.LabelFrame(self, text="3) 采集参数")
        frm_opts.pack(fill="x", padx=10, pady=8)

        self._num_entry(frm_opts, "每频道单集上限", self.max_episodes_var, 0, 0)
        self._num_entry(frm_opts, "字段勘探频道数", self.discovery_channels_var, 0, 2)
        self._num_entry(frm_opts, "字段勘探单集数", self.discovery_episodes_var, 0, 4)

        self._num_entry(frm_opts, "超时(秒)", self.timeout_var, 1, 0)
        self._num_entry(frm_opts, "重试次数", self.retries_var, 1, 2)
        self._num_entry(frm_opts, "sleep_min", self.sleep_min_var, 1, 4)
        self._num_entry(frm_opts, "sleep_max", self.sleep_max_var, 1, 6)

        ttk.Checkbutton(frm_opts, text="抓取后运行字段勘探", variable=self.run_discover_var).grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        frm_actions = ttk.LabelFrame(self, text="4) 执行")
        frm_actions.pack(fill="x", padx=10, pady=8)

        ttk.Button(frm_actions, text="开始采集", command=self.start_run).pack(side="left", padx=8, pady=6)
        ttk.Button(frm_actions, text="清空日志", command=self.clear_log).pack(side="left", padx=8, pady=6)

        frm_log = ttk.LabelFrame(self, text="运行日志")
        frm_log.pack(fill="both", expand=True, padx=10, pady=8)
        self.log_text = tk.Text(frm_log, height=18)
        self.log_text.pack(fill="both", expand=True)

    def _num_entry(self, parent, label, var, row, col):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="e", padx=6, pady=4)
        ttk.Entry(parent, textvariable=var, width=8).grid(row=row, column=col + 1, sticky="w", padx=6, pady=4)

    def log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _drain_logs(self) -> None:
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
        self.after(120, self._drain_logs)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def pick_channels(self) -> None:
        p = filedialog.askopenfilename(title="选择 channels.txt", filetypes=[("Text", "*.txt"), ("All", "*")])
        if p:
            self.channels_var.set(p)

    def pick_auth(self) -> None:
        p = filedialog.asksaveasfilename(title="选择 auth.json", defaultextension=".json", filetypes=[("JSON", "*.json"), ("All", "*")])
        if p:
            self.auth_var.set(p)

    def pick_out_dir(self) -> None:
        p = filedialog.askdirectory(title="选择输出目录")
        if p:
            self.out_var.set(p)

    def open_login(self) -> None:
        webbrowser.open(LOGIN_URL)
        self.log(f"已尝试打开登录页: {LOGIN_URL}")

    def save_auth(self) -> None:
        token = self.token_var.get().strip()
        cookie = self.cookie_var.get().strip()
        if not token and not cookie:
            messagebox.showwarning("提示", "token 和 cookie 至少填写一个")
            return
        path = Path(self.auth_var.get().strip())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"x_jike_access_token": token, "cookie": cookie}, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(f"已保存 auth: {path}")
        messagebox.showinfo("完成", f"已保存 {path}")

    def load_auth(self) -> None:
        path = Path(self.auth_var.get().strip())
        if not path.exists():
            messagebox.showwarning("提示", f"未找到文件: {path}")
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.token_var.set(str(data.get("x_jike_access_token") or ""))
        self.cookie_var.set(str(data.get("cookie") or ""))
        self.log(f"已加载 auth: {path}")

    def start_run(self) -> None:
        t = threading.Thread(target=self._run_job, daemon=True)
        t.start()

    def _run_job(self) -> None:
        try:
            channels = Path(self.channels_var.get().strip())
            auth_file = Path(self.auth_var.get().strip())
            out_dir = Path(self.out_var.get().strip())

            if not channels.exists():
                raise FileNotFoundError(f"频道文件不存在: {channels}")
            if not auth_file.exists():
                self.log("未检测到 auth.json，将以空 token/cookie 请求（可能只能拿公开数据或失败）。")

            ns_crawl = type("Args", (), {
                "channels": str(channels),
                "out_dir": str(out_dir),
                "auth_file": str(auth_file),
                "token": self.token_var.get().strip(),
                "cookie": self.cookie_var.get().strip(),
                "max_episodes": int(self.max_episodes_var.get()),
                "timeout": int(self.timeout_var.get()),
                "retries": int(self.retries_var.get()),
                "sleep_min": float(self.sleep_min_var.get()),
                "sleep_max": float(self.sleep_max_var.get()),
            })

            self.log("开始抓取...")
            ch, ep, rp = crawler.run(ns_crawl)
            self.log(f"抓取完成: {ch}")
            self.log(f"抓取完成: {ep}")
            self.log(f"抓取报告: {rp}")

            if self.run_discover_var.get():
                ns_discover = type("Args", (), {
                    "channels": str(channels),
                    "out": str(out_dir / "field_discovery.csv"),
                    "auth_file": str(auth_file),
                    "token": self.token_var.get().strip(),
                    "cookie": self.cookie_var.get().strip(),
                    "max_channels": int(self.discovery_channels_var.get()),
                    "max_episodes": int(self.discovery_episodes_var.get()),
                    "timeout": int(self.timeout_var.get()),
                    "retries": max(1, int(self.retries_var.get())),
                    "sleep_min": float(self.sleep_min_var.get()),
                    "sleep_max": float(self.sleep_max_var.get()),
                })
                self.log("开始字段勘探...")
                out = discover.run(ns_discover)
                self.log(f"字段勘探完成: {out}")

            self.log("全部任务完成。")
            messagebox.showinfo("完成", "任务已完成，请查看日志和输出目录。")
        except Exception as e:
            self.log(f"执行失败: {e}")
            self.log(traceback.format_exc())
            messagebox.showerror("失败", f"执行失败: {e}")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
