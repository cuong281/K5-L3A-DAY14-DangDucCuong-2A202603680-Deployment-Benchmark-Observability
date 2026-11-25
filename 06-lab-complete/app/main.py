"""
Production AI Agent — Part 6 Final Project

Kiểm tra đủ 12 tiêu chí:
    python check_production_ready.py
"""
import logging
import time
from contextlib import asynccontextmanager

import redis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.logging_config import log_event, setup_logging

setup_logging(settings.log_level)  # trước các import có thể ghi log

from app.auth import verify_api_key  # noqa: E402
from app.cost_guard import check_budget, estimate_tokens, record_cost  # noqa: E402
from app.rate_limiter import check_rate_limit  # noqa: E402
from app.redis_client import r, redis_healthy  # noqa: E402
from utils.mock_llm import ask as llm_ask  # noqa: E402

logger = logging.getLogger("agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Không tự đăng ký handler SIGTERM: uvicorn đã ngừng nhận kết nối mới và chờ request
    đang chạy xong rồi mới chạy phần sau yield. Ở đây chỉ cần dọn tài nguyên."""
    log_event(logger, "startup", environment=settings.environment)
    yield
    r.close()
    log_event(logger, "shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Mỗi request một dòng log. Không ghi header, API key hay nội dung câu hỏi.

    Lỗi không lường trước: ghi traceback vào log, client chỉ nhận thông báo chung.
    """
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error")
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    log_event(logger, "request", method=request.method, path=request.url.path,
              status=response.status_code, ms=round((time.perf_counter() - start) * 1000, 1))
    return response


@app.exception_handler(redis.RedisError)
async def redis_error(request: Request, exc: redis.RedisError):
    """Mất Redis thì từ chối (fail closed): không kiểm được rate limit và budget
    thì không gọi LLM. Không trả nội dung lỗi vì có thể chứa địa chỉ nội bộ."""
    log_event(logger, "redis_unavailable", logging.ERROR, error=type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"},
                        headers={"Retry-After": "5"})


@app.get("/health")
def health():
    """Liveness: process còn phản hồi là 200. Không kiểm tra Redis, vì restart app không
    sửa được Redis; nếu phụ thuộc thì Redis chết sẽ làm mọi instance bị restart."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness: 503 khi Redis không kết nối được, để load balancer ngừng gửi traffic."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis is not available")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    cost = record_cost(estimate_tokens(body.question), estimate_tokens(answer))
    return {"question": body.question, "answer": answer, "cost_usd": cost}
