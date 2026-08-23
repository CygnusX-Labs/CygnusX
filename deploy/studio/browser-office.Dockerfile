# OmicStudio 独立浏览器/文档能力镜像。
# 先构建 base，再执行：
# docker build --build-arg OMICHUB_IMAGE_TAG=v0.0.2dev \
#   -t omichub-sandbox-browser-office:v0.0.2dev \
#   -f deploy/studio/browser-office.Dockerfile deploy/studio
FROM omichub-sandbox-bio:${OMICHUB_IMAGE_TAG}

USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    CHROME_BIN=/usr/bin/chromium \
    PYTHONPATH=/opt/sandbox

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        libreoffice-writer \
        libreoffice-calc \
        libreoffice-impress \
        fonts-liberation \
    && pip install --no-cache-dir playwright python-docx python-pptx \
    && python -m playwright install chromium \
    && mkdir -p /opt/playwright-browsers /tmp/chromium /tmp/downloads \
    && chown -R 10001:10001 /opt/playwright-browsers /tmp/chromium /tmp/downloads \
    && rm -rf /var/lib/apt/lists/*

USER 10001
WORKDIR /workspace
CMD ["sh", "-c", "rm -f /workspace/.agent.sock && exec uvicorn --app-dir /opt/sandbox sandbox_agent:app --uds /workspace/.agent.sock"]
