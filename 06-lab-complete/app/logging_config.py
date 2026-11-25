"""
Structured logging (tiêu chí 10): mỗi dòng log của app là một JSON object hợp lệ.

Cả dòng được tạo bằng một lần json.dumps. Không ghép chuỗi JSON bằng tay, vì dấu nháy
hoặc xuống dòng trong message sẽ làm hỏng JSON.
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Field bổ sung, vd log_event(logger, "request", path="/ask", status=200)
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(level: str) -> None:
    """Gọi trước mọi dòng log khác.

    Gán thẳng handler cho root thay vì dùng basicConfig: basicConfig không làm gì
    nếu root đã có handler, nên dễ mất cấu hình JSON mà không báo lỗi.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})
