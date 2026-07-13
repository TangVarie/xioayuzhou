# 小宇宙·追光数据 → 飞书多维表格同步

一个挂在 Railway 上的轻量服务：在飞书多维表格里点击按钮 → 服务后台用 Playwright 登录 `zhuiguang.xyz` 抓取该频道的 9 个基础数据字段 → 自动写回当前行。

## 数据流

```
飞书表格 ──点按钮── 飞书自动化(HTTP) ──POST── Railway 服务
                                              │
                                              ├─ 读这一行的「节目详情追光链接」
                                              ├─ Playwright(headless) 注入登录态 → 抓 zhuiguang
                                              └─ 写回 9 个字段
登录态过期：管理员浏览器访问 /admin/login，
            在嵌入的 noVNC 里登录一次，state 加密后写到 Railway Volume
```

服务**没有任何外部数据库依赖**，所有持久数据（登录态、抓取日志）都写在 Railway Volume 里。

## 抓取字段

| 列名 | 类型 | 写入格式 |
|------|------|---------|
| 订阅数 | 数字 | 整数 |
| 平均收听量 | 数字 | 整数 |
| 平均节目时长 | 数字 | 分钟（浮点） |
| 平均播放时长 | 数字 | 分钟（浮点） |
| 平均评论数 | 数字 | 整数/浮点 |
| 订阅用户女性占比 | 进度 | 0~1 浮点 |
| 订阅用户主要年龄分布 | 多选 | 字符串数组 |
| 用户主要地域分布 | 多选 | 字符串数组 |
| 订阅用户设备iphone占比 | 进度 | 0~1 浮点 |

## 部署到 Railway

### 1. 准备飞书侧
跟着 [`docs/feishu_setup.md`](./docs/feishu_setup.md) 走完：
- 创建自建应用、申请 `bitable:app` 权限并发布
- 把应用加进目标多维表格
- 在表格里加按钮列、配置自动化流程发 POST 到 `/feishu/trigger`
- 可选：再加一个"全表刷新"按钮，body 改成 `{ "scan_all": true }`

### 2. 部署到 Railway
1. Fork / push 本仓库到 GitHub。
2. Railway → `New Project` → `Deploy from GitHub repo`，选这个仓库，会识别 `Dockerfile` 直接构建。
3. **加 Volume**：服务 `Settings → Volumes → New Volume`，挂载点填 `/data`，大小默认 1GB 就够（登录态加日志几 KB 量级）。
4. 在 `Variables` 里设置环境变量（参考 [`.env.example`](./.env.example)）。
   - `FERNET_KEY` 用以下命令本地生成一次：
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   - `STATE_DIR` 默认就是 `/data`，不用改（Dockerfile 里已经设了默认值）。
5. 在 `Settings → Networking` 里 `Generate Domain` 拿到一个公网域名。
6. 把这个域名填回飞书自动化流程的 URL（`https://<域名>/feishu/trigger`）。

### 3. 第一次登录 zhuiguang.xyz
1. 浏览器打开 `https://<你的域名>/admin/login?token=<ADMIN_TOKEN>`。
2. 顶部点 **启动浏览器**，**等 2~3 秒**虚拟桌面拉起后，下方的 noVNC 区域里会出现一个真实 Chrome。
3. 在那个浏览器里登录 zhuiguang.xyz。
4. 顶部状态变成 `saved` 表示登录态已加密写到 `/data/storage_state.enc`，桌面会自动释放，可关闭页面。

> 虚拟桌面（Xvfb/x11vnc/websockify）是**按需启动**的：只有点"启动浏览器"时才拉起，登录成功或 10 分钟无操作后自动关闭。平时不占内存，所以日常空闲时容器只跑 uvicorn + nginx，省钱。
5. 之后任何用户在飞书里点按钮都能直接抓数据；登录态失效时再来这一步即可。

> 不想搞 noVNC 也可以本地用 Playwright 跑一次登录，把 `storage_state.json` 上传：
> ```bash
> curl -F "file=@storage_state.json" \
>   "https://<域名>/admin/upload-state?token=<ADMIN_TOKEN>"
> ```

## 批量 / 定时刷新

### 1) 飞书"全表刷新"按钮（推荐）
在飞书表格里随便挑一行放个按钮：
- 自动化流程 → 发送 HTTP 请求 → URL 还是 `https://<域名>/feishu/trigger`
- Body 改成：
  ```json
  { "scan_all": true }
  ```
- 服务收到后会异步跑全表，立刻返回 `{"accepted": true, "mode": "scan_all"}`。

### 2) 定时跑（飞书自动化的定时触发器）
飞书自动化流程的触发器换成 **"按指定时间触发"**（每天/每周/每小时都行），动作仍是发送 HTTP 请求到 `/feishu/trigger`，body 还是 `{ "scan_all": true }`。
服务自己**不内置 cron**，定时这件事完全交给飞书排期，没有重复机制。

### 3) 直接打 API（运维用）
```bash
curl -X POST "https://<域名>/admin/scan-all?token=<ADMIN_TOKEN>"               # 异步
curl -X POST "https://<域名>/admin/scan-all?token=<ADMIN_TOKEN>&wait=true"     # 同步等完
curl "https://<域名>/admin/scan-status?token=<ADMIN_TOKEN>"                    # 看进度
```

行内单点按钮仍然有用：只刷某一行的话比扫全表更省时间。

## 可调参数（Railway → Variables）

只暴露真正"业务可变"的，技术细节都在代码里。完整清单见 [`.env.example`](./.env.example)。

### 必填（没默认值）
| 变量 | 说明 |
|---|---|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书自建应用凭证 |
| `FEISHU_APP_TOKEN` / `FEISHU_TABLE_ID` | 目标多维表 |
| `FEISHU_WEBHOOK_SECRET` | 飞书 webhook 校验密钥（自己生成） |
| `ADMIN_TOKEN` | 保护 /admin/* 的密钥（自己生成） |
| `FERNET_KEY` | 加密登录态用的密钥（用 `Fernet.generate_key()` 生成） |

### 飞书表列名（默认对应当前表头，改飞书列名时同步改）
`FEISHU_LINK_FIELD`、`FIELD_SUBSCRIBERS`、`FIELD_AVG_LISTEN`、`FIELD_AVG_DURATION`、`FIELD_AVG_PLAY`、`FIELD_AVG_COMMENTS`、`FIELD_FEMALE_RATIO`、`FIELD_AGE_DISTRIBUTION`、`FIELD_LOCATION_DISTRIBUTION`、`FIELD_IPHONE_RATIO`

### 持久化
| 变量 | 默认 | 说明 |
|---|---|---|
| `STATE_DIR` | `/data` | Volume 挂载点（本地开发改成 `./data`） |

> 改了任何 Variables，Railway 会自动重启服务；几十秒后新值生效。
>
> 抓取超时、屏幕分辨率、登录判定 URL、ready selector 这些纯实现细节都不在 env 里——它们跟飞书表无关，要调就改代码（`app/scraper.py`、`app/login_session.py`）然后重新部署。

## 调试

- `GET /healthz` — 健康检查，会返回是否已有登录态。
- `GET /admin/debug?token=<ADMIN_TOKEN>&url=<频道 URL>` — 抓一次但不写飞书，返回提取到的字段、缺失字段、页面 text 预览、所有 XHR URL。
- `POST /admin/run?token=<ADMIN_TOKEN>&record_id=<rec_xxx>` — 模拟一次完整流程（不需要飞书按钮触发）。
- `GET /admin/log?token=<ADMIN_TOKEN>&n=100` — 拉 `/data/scrape_log.jsonl` 最后 N 条记录。
- `POST /admin/clear-state?token=<ADMIN_TOKEN>` — 清除登录态。

抓到的字段在 zhuiguang 真实页面上的位置/单位（万、分钟、%）会有差异，**首次部署后请用 `/admin/debug` 跑一两条**，看返回的 `fields`/`missing`/`page_text_preview`，必要时在 `app/scraper.py` 里微调正则。

## 本地跑

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env  # 填好后，本地 STATE_DIR 改成 ./data
mkdir -p data
uvicorn app.main:app --reload --port 8000
```

本地无 Xvfb，所以 `/admin/login` 的"启动浏览器"会直接弹出真实窗口（headed），登录完成后照样会写 state 到本地 `data/` 目录。

## 安全说明

- 所有 `/admin/*` 路由都受 `ADMIN_TOKEN` 保护，泄漏后请立即换。
- 登录态在 Volume 上用 Fernet 对称加密，密钥仅在 Railway 环境变量里。即便有人能访问 Volume 文件也读不出明文。
- `/feishu/trigger` 使用 `X-Trigger-Secret` 校验请求来自飞书自动化（与飞书 webhook 节点的 Header 一致即可）。

## 已知限制

- zhuiguang.xyz 页面结构若改版，需调整 `app/scraper.py` 的正则/选择器。
- 单实例服务，并发抓取会被 Playwright 串行化（高并发时可加队列）。
- noVNC 虚拟桌面按需启动：仅登录时拉起，登录完/超时自动关；空闲时只剩 uvicorn + nginx，常驻内存很低。
- 抓取用的 headless Chromium 每次抓完即关；配合 `MALLOC_ARENA_MAX=2` 抑制长驻进程的内存高水位。
- 定时刷新完全交给飞书自动化的"按时间触发"，服务自身不跑 cron。
- Railway Volume 不会随服务重启丢失，但**销毁服务/项目时会一起销毁**，记得迁移前先备份 `/data` 里的文件。
