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
            在嵌入的 noVNC 里登录一次，state 自动加密保存到 Supabase
```

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

## 部署到 Railway（最短路径）

### 1. 准备 Supabase
- 新建一个 project（已经有了就直接用）。
- 在 SQL Editor 里跑一次 [`docs/supabase_schema.sql`](./docs/supabase_schema.sql)，会建 `auth_state` 和 `scrape_log` 两张表。
- 从 `Settings → API` 拿到 `SUPABASE_URL` 和 `service_role` key。

### 2. 准备飞书侧
跟着 [`docs/feishu_setup.md`](./docs/feishu_setup.md) 走完：
- 创建自建应用、申请 `bitable:app` 权限并发布
- 把应用加进目标多维表格
- 在表格里加按钮列、配置自动化流程发 POST 到 `/feishu/trigger`

### 3. 部署到 Railway
1. Fork / push 本仓库到 GitHub。
2. Railway → `New Project` → `Deploy from GitHub repo`，选这个仓库。
3. Railway 会识别 `Dockerfile` 直接构建。
4. 在 `Variables` 里设置环境变量（参考 [`.env.example`](./.env.example)）。
   - `FERNET_KEY` 用以下命令本地生成一次：
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
5. 在 `Settings → Networking` 里 `Generate Domain` 拿到一个公网域名。
6. 把这个域名填回飞书自动化流程的 URL（`https://<域名>/feishu/trigger`）。

### 4. 第一次登录 zhuiguang.xyz
1. 浏览器打开 `https://<你的域名>/admin/login?token=<ADMIN_TOKEN>`。
2. 顶部点 **启动浏览器**，下方的 noVNC 区域里会出现一个真实 Chrome。
3. 在那个浏览器里登录 zhuiguang.xyz。
4. 顶部状态变成 `saved` 表示登录态已加密存到 Supabase，可关闭页面。
5. 之后任何用户在飞书里点按钮都能直接抓数据；登录态失效时再来这一步即可。

> 如果你不想搞 noVNC（例如对资源敏感），也可以在本地用 Playwright 跑一次登录，把 `storage_state.json` 通过 `POST /admin/upload-state?token=<ADMIN_TOKEN>` 上传：
> ```bash
> curl -F "file=@storage_state.json" \
>   "https://<域名>/admin/upload-state?token=<ADMIN_TOKEN>"
> ```

## 调试

- `GET /healthz` — 健康检查，会返回是否已有登录态。
- `GET /admin/debug?token=<ADMIN_TOKEN>&url=<频道 URL>` — 抓一次但不写飞书，返回提取到的字段、缺失字段、页面 text 预览、所有 XHR URL；用来确认 selector/正则在你那边的真实页面上是否对得上。
- `POST /admin/run?token=<ADMIN_TOKEN>&record_id=<rec_xxx>` — 模拟一次完整流程（不需要飞书按钮触发）。
- `POST /admin/clear-state?token=<ADMIN_TOKEN>` — 清除登录态。

抓到的字段在 zhuiguang 真实页面上的位置/单位（万、分钟、%）会有差异，**首次部署后请用 `/admin/debug` 跑一两条**，看返回的 `fields`/`missing`/`page_text_preview`，必要时在 `app/scraper.py` 里微调正则。

## 本地跑

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env  # 填好后
uvicorn app.main:app --reload --port 8000
```

本地无 Xvfb，所以 `/admin/login` 的"启动浏览器"会直接弹出真实窗口（headed），登录完成后照样会写 state 到 Supabase。

## 安全说明

- 所有 `/admin/*` 路由都受 `ADMIN_TOKEN` 保护，泄漏后请立即换。
- 登录态使用 Fernet 对称加密后存 Supabase，密钥仅在 Railway 环境变量里。
- `/feishu/trigger` 使用 `X-Trigger-Secret` 校验请求来自飞书自动化（与飞书 webhook 节点的 Header 一致即可）。
- 不要把 service_role key 暴露在前端；它具有绕过 RLS 的能力。

## 已知限制

- zhuiguang.xyz 页面结构若改版，需调整 `app/scraper.py` 的正则/选择器。
- 单实例服务，并发抓取会被 Playwright 串行化（高并发时可加队列）。
- noVNC 仅在登录时使用，非登录时 headed Chrome 不会驻留，资源占用很低。
