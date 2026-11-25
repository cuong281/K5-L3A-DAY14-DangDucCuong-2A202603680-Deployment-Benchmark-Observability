"""
Kết nối Redis dùng chung cho rate limiter, cost guard và /ready.

from_url() KHÔNG kết nối ngay; kết nối chỉ mở khi có lệnh đầu tiên. Vì vậy app khởi động
được cả khi Redis chưa sẵn sàng (tiêu chí 5 và yêu cầu chạy container không có Redis).
"""
import redis

from app.config import settings

# Timeout ngắn: Redis treo thì request lỗi sau 2 giây thay vì chờ vô hạn
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready: ping được Redis thì True, lỗi kết nối hoặc timeout thì False."""
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
