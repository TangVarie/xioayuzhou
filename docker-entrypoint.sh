#!/usr/bin/env bash
set -euo pipefail

# 给 supervisord 配置里的 %(ENV_*)s 占位符提供默认值
export DISPLAY="${DISPLAY:-:99}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"
export APP_PORT="${APP_PORT:-8000}"
export LISTEN_PORT="${PORT:-8080}"

envsubst '${APP_PORT} ${NOVNC_PORT} ${LISTEN_PORT}' \
  < /etc/nginx/sites-available/default \
  > /etc/nginx/sites-available/default.rendered
mv /etc/nginx/sites-available/default.rendered /etc/nginx/sites-available/default

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
