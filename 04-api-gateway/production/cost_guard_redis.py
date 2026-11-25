"""
Exercise 4.4: cost guard dùng Redis, mỗi user có budget $10/tháng.

Khác cost_guard.py (in-memory): mọi instance dùng chung một tổng chi tiêu và
restart app không làm mất số liệu.

Chạy thử (cần Redis ở localhost:6379):
    python cost_guard_redis.py
"""
import os
from datetime import datetime, timezone

import redis

MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10"))
KEY_TTL_SECONDS = 32 * 24 * 3600  # dài hơn tháng dài nhất (31 ngày)

r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

# Kiểm tra và cộng trong cùng một lệnh Lua. Redis chạy script nguyên khối, nên hai
# request đồng thời không thể cùng thấy "còn budget" rồi cùng cộng và vượt mức.
_RESERVE = r.register_script("""
local spent = tonumber(redis.call('GET', KEYS[1]) or '0')
if spent + tonumber(ARGV[1]) > tonumber(ARGV[2]) then
  return 0
end
redis.call('INCRBYFLOAT', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
""")


def budget_key(user_id: str, now: datetime | None = None) -> str:
    """Key có năm-tháng (UTC): sang tháng mới là key mới, tức budget tự về 0."""
    now = now or datetime.now(timezone.utc)
    return f"budget:{user_id}:{now:%Y-%m}"


def check_budget(user_id: str, estimated_cost: float, now: datetime | None = None) -> bool:
    """True nếu còn budget (và đã ghi nhận estimated_cost), False nếu vượt."""
    if estimated_cost < 0:
        raise ValueError("estimated_cost must be >= 0")
    allowed = _RESERVE(
        keys=[budget_key(user_id, now)],
        args=[estimated_cost, MONTHLY_BUDGET_USD, KEY_TTL_SECONDS],
    )
    return allowed == 1


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor

    nov = datetime(2026, 11, 25, tzinfo=timezone.utc)
    dec = datetime(2026, 12, 1, tzinfo=timezone.utc)
    users = ["demo-user", "other-user", "parallel-user"]
    r.delete(*[budget_key(u, m) for u in users for m in (nov, dec)])

    print("1. $6   :", check_budget("demo-user", 6, nov))
    print("2. $4   :", check_budget("demo-user", 4, nov), "(vừa đủ $10)")
    print("3. $0.01:", check_budget("demo-user", 0.01, nov), "(vượt $10)")
    print("4. user khác $6      :", check_budget("other-user", 6, nov))
    print("5. demo-user tháng 12:", check_budget("demo-user", 6, dec))
    print("6. tổng tháng 11     :", r.get(budget_key("demo-user", nov)))
    print("7. TTL (ngày)        :", r.ttl(budget_key("demo-user", nov)) // 86400)

    with ThreadPoolExecutor(20) as pool:
        ok = sum(pool.map(lambda _: check_budget("parallel-user", 1, nov), range(50)))
    print("8. 50 request $1 song song, được duyệt:", ok)
