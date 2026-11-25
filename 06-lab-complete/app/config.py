"""
Config theo 12-Factor: mọi cấu hình đọc từ biến môi trường (tiêu chí 9).

Giá trị mặc định chỉ để chạy local. Secret (AGENT_API_KEY) không có mặc định.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Nạp .env khi chạy local. Biến đã có sẵn trong môi trường luôn được ưu tiên
# (override=False), nên trên cloud file này không ảnh hưởng gì.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


def _env(name: str, default: str):
    return field(default_factory=lambda: os.getenv(name, default).strip())


def _env_int(name: str, default: int):
    return field(default_factory=lambda: int(os.getenv(name, str(default))))


def _env_float(name: str, default: float):
    return field(default_factory=lambda: float(os.getenv(name, str(default))))


@dataclass(frozen=True)
class Settings:
    port: int = _env_int("PORT", 8000)
    environment: str = _env("ENVIRONMENT", "development")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip().upper())

    # repr=False: in settings ra log cũng không lộ key hay mật khẩu Redis
    agent_api_key: str = field(
        default_factory=lambda: os.getenv("AGENT_API_KEY", "").strip(), repr=False)
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(), repr=False)

    rate_limit_per_minute: int = _env_int("RATE_LIMIT_PER_MINUTE", 10)
    daily_budget_usd: float = _env_float("DAILY_BUDGET_USD", 1.0)
    monthly_budget_usd: float = _env_float("MONTHLY_BUDGET_USD", 10.0)

    def __post_init__(self):
        """Fail fast: cấu hình sai thì dừng ngay khi khởi động, không đợi tới lúc có request."""
        if self.environment == "production" and not self.agent_api_key:
            raise ValueError("AGENT_API_KEY must be set when ENVIRONMENT=production")
        if self.rate_limit_per_minute < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be >= 1")
        if self.daily_budget_usd < 0 or self.monthly_budget_usd < 0:
            raise ValueError("DAILY_BUDGET_USD and MONTHLY_BUDGET_USD must be >= 0")


settings = Settings()
