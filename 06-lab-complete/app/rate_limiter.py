"""
Rate limiting (tiêu chí 7): sliding window 60 giây, state trong Redis.

Mỗi API key có một sorted set, mỗi request được chấp nhận là một phần tử có
score = thời điểm gửi. Đếm số phần tử trong 60 giây gần nhất là biết đã dùng bao nhiêu lượt.
"""
import hashlib
import math
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60

# Xoá cũ → đếm → thêm phải là một khối: nếu tách thành nhiều lệnh, hai worker có thể cùng
# đếm được "còn 1 lượt" rồi cùng thêm. Redis chạy script Lua nguyên khối nên không bị vậy.
# Dùng đồng hồ của Redis (TIME) để mọi instance tính theo cùng một mốc thời gian.
# Trả về 0 nếu được phép, ngược lại là số mili-giây phải chờ.
_SLIDING_WINDOW = r.register_script("""
local t = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)
local window = tonumber(ARGV[1])

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[2]) then
  redis.call('ZADD', KEYS[1], now, ARGV[3])
  redis.call('PEXPIRE', KEYS[1], window)
  return 0
end
local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
return math.max(1, tonumber(oldest[2]) + window - now)
""")


def check_rate_limit(key: str) -> None:
    """Vượt RATE_LIMIT_PER_MINUTE trong 60 giây → 429 kèm Retry-After."""
    # Băm key: ai đọc được Redis cũng không lấy được API key
    key_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    wait_ms = _SLIDING_WINDOW(
        keys=[f"ratelimit:{key_id}"],
        args=[WINDOW_SECONDS * 1000, settings.rate_limit_per_minute, uuid.uuid4().hex],
    )
    if wait_ms > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} requests per minute",
            headers={"Retry-After": str(math.ceil(wait_ms / 1000))},
        )
