FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # 限制 glibc 内存分配 arena 数量，并积极把空闲内存还给系统。
    # 长驻的 uvicorn 进程每次跑完一次 headless 抓取后，Chromium 子进程虽然退出，
    # 但 glibc 默认会保留已申请的堆区导致 RSS 高水位一直不降；下面两项能显著缓解。
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=65536

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    xvfb \
    x11vnc \
    fluxbox \
    novnc \
    websockify \
    nginx \
    gettext-base \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && python -m playwright install chromium

COPY app /app/app
COPY supervisord.conf /etc/supervisor/conf.d/app.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY nginx.conf /etc/nginx/sites-available/default
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

ENV DISPLAY=:99 \
    NOVNC_PORT=6080 \
    APP_PORT=8000 \
    STATE_DIR=/data

RUN mkdir -p /data

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
