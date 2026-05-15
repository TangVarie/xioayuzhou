#!/usr/bin/env bash
set -euo pipefail

# 所有变量都给一个默认值，确保 supervisord 配置里的 %(ENV_*)s 不会因未定义而启动失败
export DISPLAY="${DISPLAY:-:99}"
export SCREEN_WIDTH="${SCREEN_WIDTH:-1440}"
export SCREEN_HEIGHT="${SCREEN_HEIGHT:-900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"
export APP_PORT="${APP_PORT:-8000}"
export LISTEN_PORT="${PORT:-8080}"

envsubst '${APP_PORT} ${NOVNC_PORT} ${LISTEN_PORT}' \
  < /etc/nginx/sites-available/default \
  > /etc/nginx/sites-available/default.rendered
mv /etc/nginx/sites-available/default.rendered /etc/nginx/sites-available/default

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
