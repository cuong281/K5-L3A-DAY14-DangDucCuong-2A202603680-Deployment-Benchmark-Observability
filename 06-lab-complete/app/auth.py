"""
API Key authentication (tiêu chí 6).

Client gửi header X-API-Key. Thiếu hoặc sai key → 401.
"""
import secrets

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

# auto_error=False: FastAPI không tự trả lỗi khi thiếu header, để ta tự trả 401
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency cho /ask. Trả về key hợp lệ để rate limiter dùng làm định danh."""
    expected = settings.agent_api_key
    # Chưa cấu hình key thì từ chối tất cả, không được hiểu là "không cần key"
    valid = bool(expected and api_key) and secrets.compare_digest(
        api_key.encode(), expected.encode())
    if not valid:
        # Cùng một thông báo cho thiếu và sai key, không gợi ý cho kẻ dò key
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    return api_key
