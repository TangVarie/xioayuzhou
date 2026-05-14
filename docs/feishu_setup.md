# 飞书侧配置步骤

## 1. 创建自建应用，拿到 app_id / app_secret

1. 进入 [飞书开放平台](https://open.feishu.cn/app) → 我的应用 → 创建企业自建应用。
2. 在 **凭证与基础信息** 复制 `App ID` 和 `App Secret`，对应 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`。
3. 在 **权限管理** 里申请以下权限并发布：
   - `bitable:app`（多维表格读写）
   - `bitable:app:readonly`（兜底，可选）
4. 在 **版本管理与发布** 里发布一个版本。

## 2. 把应用加进多维表格

1. 打开你的多维表格（`https://feishu.cn/base/VDGEwFu8mipstnkxCclcXvqFngh`）。
2. 右上角 `...` → `更多` → `添加应用`，搜索刚才创建的应用，添加为协作者并给"可编辑"权限。

## 3. 配置按钮列 + 自动化流程

1. 在表格里新增一列，类型选 **按钮**，名字随意（例如 `刷新数据`）。
2. 按钮的"操作"选 **触发自动化流程**。
3. 新建自动化流程：
   - 触发器：**点击按钮时**
   - 执行：**发送 HTTP 请求**
     - URL: `https://<你的 Railway 域名>/feishu/trigger`
     - 方法: `POST`
     - Header:
       - `Content-Type`: `application/json`
       - `X-Trigger-Secret`: `<和 FEISHU_WEBHOOK_SECRET 一致>`
     - Body（JSON）:
       ```json
       {
         "record_id": "{{触发记录.记录ID}}"
       }
       ```
       注意"触发记录.记录ID"是飞书里选择字段时给出的占位变量，UI 会自动渲染成 `{{rec_xxx}}`。
4. 保存并启用流程。

## 4. 字段名要求

九个数据列的列名必须与下面一致（不要加空格或符号）：

| 列名 | 列类型 |
|------|--------|
| 订阅数 | 数字 |
| 平均收听量 | 数字 |
| 平均节目时长 | 数字 |
| 平均播放时长 | 数字 |
| 平均评论数 | 数字 |
| 订阅用户女性占比 | 进度 |
| 订阅用户主要年龄分布 | 多选 |
| 用户主要地域分布 | 多选 |
| 订阅用户设备iphone占比 | 进度 |

频道链接列名必须叫 `节目详情追光链接`（也可以通过 `FEISHU_LINK_FIELD` 环境变量改名）。
