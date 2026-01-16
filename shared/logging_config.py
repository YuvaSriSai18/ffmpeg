"""Structured JSON logging configuration."""
import logging
import json
import sys
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Format logs as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "job_id"):
            log_data["job_id"] = record.job_id

        return json.dumps(log_data)


def setup_logging(level: str = "INFO", service_name: str = "stt-service"):
    """Configure logging for the service."""
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers = []

    # Create handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Set initial log level for root logger
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[handler],
    )

    logger.info(f"Logging initialized for {service_name}", extra={"service": service_name})
    return logger
