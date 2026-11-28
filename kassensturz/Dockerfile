FROM python:3.14-slim-trixie@sha256:f57c4c23b985d95deea5bc5249e2f9c8a512b4cc9d5d3fd31900cbd2f5f0a604

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY app/ /app/

LABEL io.hass.type="addon" \
      io.hass.name="Kassensturz"

HEALTHCHECK --interval=60s --timeout=6s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/healthz', timeout=4).read()"]

CMD ["python", "-m", "kassensturz"]
