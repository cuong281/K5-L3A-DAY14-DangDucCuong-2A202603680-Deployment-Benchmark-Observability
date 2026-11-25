"""
Cost guard (tiêu chí 8): cộng dồn chi phí LLM vào Redis, hết budget → 402.

Tổng chi phí tính chung cho cả agent, theo ngày và theo tháng (giờ UTC).
"""
import logging
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.logging_config import log_event
from app.redis_client import r

logger = logging.getLogger("agent.cost")

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAY_TTL_SECONDS = 2 * 24 * 3600
MONTH_TTL_SECONDS = 32 * 24 * 3600


def estimate_tokens(text: str) -> int:
    """Mock LLM không trả số token nên ước lượng khoảng 4 ký tự / token."""
    return max(1, len(text) // 4)


def _keys() -> tuple[str, str]:
    """Ngày/tháng nằm trong key: sang kỳ mới là key mới, tổng tự về 0, không cần job reset."""
    now = datetime.now(timezone.utc)
    return f"cost:day:{now:%Y-%m-%d}", f"cost:month:{now:%Y-%m}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget ngày hoặc tháng → 402."""
    day, month = (float(v or 0) for v in r.mget(*_keys()))
    if day >= settings.daily_budget_usd or month >= settings.monthly_budget_usd:
        # Không ghi số tiền vào response: đó là thông tin nội bộ, chỉ ghi trong log
        log_event(logger, "budget_exceeded", logging.WARNING, day_usd=day, month_usd=month)
        raise HTTPException(status_code=402, detail="Budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào tổng ngày và tháng, trả về chi phí request."""
    cost = (input_tokens * PRICE_INPUT_PER_1K + output_tokens * PRICE_OUTPUT_PER_1K) / 1000
    day_key, month_key = _keys()
    try:
        with r.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(day_key, cost).expire(day_key, DAY_TTL_SECONDS)
            pipe.incrbyfloat(month_key, cost).expire(month_key, MONTH_TTL_SECONDS)
            pipe.execute()
    except redis.RedisError as exc:
        # LLM đã trả lời rồi: vẫn trả kết quả cho người dùng, ghi log để đối soát sau
        log_event(logger, "cost_not_recorded", logging.ERROR, cost_usd=cost,
                  error=type(exc).__name__)
    return cost
