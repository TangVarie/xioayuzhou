# 小宇宙频道数据轻量采集脚本（手动触发 + CSV 输出）

> 目标：100 个频道，手动执行一次即采集一次，并立即输出 CSV。

## 功能

- 从 `channels.txt` 读取频道 ID 或频道 URL。
- 调用小宇宙移动端常见接口（`/v1/podcast/get`、`/v1/episode/list`）。
- 导出：
  - `channels_snapshot_*.csv`
  - `episodes_snapshot_*.csv`
  - `crawl_report_*.csv`
- 支持字段勘探：
  - 运行 `discover.py` 自动统计响应中的字段路径及出现频率。

## 使用

## 本地 UI 应用（一键点点点，推荐给非技术同学）

你说的“封装成轻量本地应用、不会命令行也能用”，现在可以直接运行 GUI：

```bash
python app_gui.py
```

打开后按界面顺序操作：
1. 选择 `channels.txt`、`auth.json`、输出目录；
2. 点“打开小宇宙官网登录”，登录后把 token/cookie 粘贴到界面并保存；
3. 点“开始采集”。  

程序会在界面日志里显示进度，并把 CSV 输出到你选的目录。

---

## 本地网络一键跑（命令行推荐）

> 你问的“怎么在本地网络跑、能不能直接封装”，直接用这个：

```bash
python one_click.py --channels channels.txt --login --discover
```

这条命令会做三件事：
1. 若没有 `auth.json`，自动引导你去官网登录并保存凭据；
2. 立刻抓取频道并导出 3 个 CSV；
3. 可选再跑一份字段勘探 CSV（`--discover` 开启）。

### 1) 准备频道列表

创建 `channels.txt`，每行一个频道 ID 或 URL：

```text
6694f31be6141b61955090f4
https://www.xiaoyuzhoufm.com/podcast/5e280fab418a84a0461f9126
```

### 2) 先走官网登录桥接（推荐）

```bash
python login_bridge.py --out auth.json
```

执行后会打开官网，你登录后把浏览器中的 `x-jike-access-token` / `Cookie` 粘贴回终端，脚本会保存到 `auth.json`。
仓库也提供了 `auth.example.json` 作为模板。

### 3) 运行采集

```bash
python crawler.py --channels channels.txt --auth-file auth.json --out-dir out --max-episodes 50
```

如果你有登录态 token（普通用户可见数据），可加：

```bash
python crawler.py --channels channels.txt --out-dir out --token "<x-jike-access-token>"
```

### 4) 运行字段勘探

```bash
python discover.py --channels channels.txt --auth-file auth.json --out out/field_discovery.csv
```

## 本地执行建议

- 请在你自己的网络环境运行（当前容器环境对目标站点存在 403 隧道限制）。
- 推荐先小规模试跑：`channels.txt` 先放 3~5 个频道，验证后再放满 100 个。
- 若 `auth.json` 过期，删除后重新执行 `python one_click.py --login ...` 即可刷新凭据。

## 可选：打包成双击可运行（Windows）

如果你要发给完全不会 Python 的同事，可在本地执行：

```bash
pip install pyinstaller
pyinstaller -F -w app_gui.py -n xiaoyuzhou_crawler_gui
```

打包后可执行文件在 `dist/xiaoyuzhou_crawler_gui.exe`。

## 说明

- 本仓库只做公开/普通账号可见数据采集，不包含账号破解或绕过安全机制。
- 由于接口可能更新，建议先跑 `discover.py` 再确认最终字段口径。
- 当前运行环境如无法直连目标站点，脚本会在 `crawl_report` 记录失败原因（例如网络 403/超时）。

## 字段勘探（离线种子）

仓库提供 `field_catalog_seed.csv`，由公开的接口文档样例提取得到，便于你先做字段评审。
