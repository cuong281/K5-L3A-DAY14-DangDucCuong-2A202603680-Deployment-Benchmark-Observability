# ── Stage 1: builder ─ cài thư viện vào một virtualenv ─────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# requirements.txt trước code: sửa code không phải cài lại thư viện (layer cache)
COPY requirements.txt .
RUN pip install -r requirements.txt

# ── Stage 2: runtime ─ chỉ có thư viện đã cài và code ──────────────
FROM python:3.11-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --no-create-home app

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/
COPY utils/ ./utils/

# Code thuộc root, app chỉ có quyền đọc
USER app

EXPOSE 8000

# /health không phụ thuộc Redis. Dùng Python vì image slim không có curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.getenv('PORT', '8000')}/health\", timeout=3)" || exit 1

# exec: uvicorn thay thế sh và trở thành PID 1 để nhận SIGTERM của `docker stop`.
# Chờ request tối đa 8 giây, ngắn hơn 10 giây trước khi Docker gửi SIGKILL.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --timeout-graceful-shutdown 8"]
