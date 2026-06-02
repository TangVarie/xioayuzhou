#!/usr/bin/env bash
set -euo pipefail

# 给 supervisord 配置里的 %(ENV_*)s 占位符提供默认值
export DISPLAY="${DISPLAY:-:99}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"
export APP_PORT="${APP_PORT:-8000}"
export LISTEN_PORT="${PORT:-8080}"

echo "[entrypoint] PORT=${PORT:-(unset)} LISTEN_PORT=${LISTEN_PORT} APP_PORT=${APP_PORT} NOVNC_PORT=${NOVNC_PORT}"

# 渲染 nginx 站点配置（替换 ${LISTEN_PORT} / ${ADMIN_TOKEN} 等占位符）
# 注意：只列出我们自己的占位符，避免 envsubst 误替换 nginx 内置变量（$host 等）。
envsubst '${APP_PORT} ${NOVNC_PORT} ${LISTEN_PORT} ${ADMIN_TOKEN}' \
  < /etc/nginx/sites-available/default \
  > /etc/nginx/sites-available/default.rendered
mv /etc/nginx/sites-available/default.rendered /etc/nginx/sites-available/default

# 把 nginx 的 access/error log 重定向到容器 stdout/stderr，方便在 Railway logs 里直接看
ln -sf /dev/stdout /var/log/nginx/access.log
ln -sf /dev/stderr /var/log/nginx/error.log

# 只做语法测试；不要 cat 渲染后的配置——里面现在含 ADMIN_TOKEN，打到日志会泄露。
echo "[entrypoint] === nginx -t ==="
nginx -t || true
echo "[entrypoint] ==========================="

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
