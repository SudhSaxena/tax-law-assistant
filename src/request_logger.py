import logging
import json
import os
from datetime import datetime, timezone
from paths import LOGS_DIR, LOG_FILE_PATH

LOG_DIR = str(LOGS_DIR)
LOG_FILE = str(LOG_FILE_PATH)

os.makedirs(LOG_DIR, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Outputs each log record as a single JSON line (JSONL format) —
    easy to grep, and trivial to ingest into a real log aggregator later
    (Datadog, CloudWatch, etc.) without changing the logging calls themselves.
    """
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
        }
        # record.msg is expected to be a dict (see log_event below)
        if isinstance(record.msg, dict):
            payload.update(record.msg)
        else:
            payload["message"] = str(record.msg)
        return json.dumps(payload)


def _build_logger():
    logger = logging.getLogger("tax_assistant")
    logger.setLevel(logging.INFO)
    if not logger.handlers:  # avoid duplicate handlers on module re-import
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


logger = _build_logger()


def log_event(event, level="info", **fields):
    """Logs one structured JSON line. Usage:
        log_event("request_completed", request_id=rid, latency_ms=123, ...)
    """
    record = {"event": event, **fields}
    log_fn = getattr(logger, level, logger.info)
    log_fn(record)