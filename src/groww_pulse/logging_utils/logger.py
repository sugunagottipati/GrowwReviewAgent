import json
import logging
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, ClassVar

# Disallowed keywords that might contain PII or unredacted content
FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "author",
        "author_name",
        "user_name",
        "username",
        "reviewer",
        "reviewer_name",
        "avatar",
        "email",
        "phone",
        "phone_number",
        "raw_text",
        "raw_review",
        "review_text",
        "unredacted",
        "prompt_input",
        "prompt_output",
        "llm_input",
        "llm_output",
        "content",
        "text",
    }
)

# Permitted metadata keys for structured logs
ALLOWED_LOG_KEYS: frozenset[str] = frozenset(
    {
        "event",
        "run_id",
        "stage",
        "status",
        "count",
        "review_count",
        "records_received",
        "records_in_window",
        "pages_read",
        "sanitized_count",
        "redacted_count",
        "dropped_count",
        "too_short_count",
        "non_english_count",
        "duration_ms",
        "lookback_weeks",
        "model_id",
        "model_provider",
        "prompt_version",
        "document_id",
        "document_url",
        "gmail_draft_id",
        "error_summary",
        "rejection_reason",
        "batch_index",
        "batch_size",
        "theme_count",
        "quote_count",
        "action_count",
        "word_count",
        "dry_run",
    }
)


class PrivacyLogFilter(logging.Filter):
    """Logging filter that strips forbidden keys and enforces privacy."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Sanitize extra dictionary on the record
        if hasattr(record, "structured_data") and isinstance(record.structured_data, dict):
            record.structured_data = sanitize_log_dict(record.structured_data)
        return True


def sanitize_log_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Remove any forbidden keys or unapproved keys from log data."""
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        k_lower = k.lower()
        if k_lower in FORBIDDEN_KEYS:
            continue
        if k_lower in ALLOWED_LOG_KEYS:
            sanitized[k] = v
    return sanitized


class StructuredLogger:
    """Privacy-preserving structured logger for pipeline events."""

    _logger: ClassVar[logging.Logger | None] = None

    @classmethod
    def get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            logger = logging.getLogger("groww_pulse")
            logger.setLevel(logging.INFO)
            logger.propagate = False

            if not logger.handlers:
                handler = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    fmt="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S%z",
                )
                handler.setFormatter(formatter)
                handler.addFilter(PrivacyLogFilter())
                logger.addHandler(handler)

            cls._logger = logger
        return cls._logger

    @classmethod
    def info(cls, event: str, **kwargs: Any) -> None:
        logger = cls.get_logger()
        safe_data = sanitize_log_dict(kwargs)
        safe_data["event"] = event
        msg = json.dumps(safe_data, sort_keys=True, default=str)
        logger.info(msg, extra={"structured_data": safe_data})

    @classmethod
    def warning(cls, event: str, **kwargs: Any) -> None:
        logger = cls.get_logger()
        safe_data = sanitize_log_dict(kwargs)
        safe_data["event"] = event
        msg = json.dumps(safe_data, sort_keys=True, default=str)
        logger.warning(msg, extra={"structured_data": safe_data})

    @classmethod
    def error(cls, event: str, **kwargs: Any) -> None:
        logger = cls.get_logger()
        safe_data = sanitize_log_dict(kwargs)
        safe_data["event"] = event
        msg = json.dumps(safe_data, sort_keys=True, default=str)
        logger.error(msg, extra={"structured_data": safe_data})


@contextmanager
def timed_stage(stage_name: str, **kwargs: Any) -> Generator[dict[str, Any], None, None]:
    """Context manager to log duration and outcomes of pipeline stages."""
    start_time = time.perf_counter()
    StructuredLogger.info(f"stage_started:{stage_name}", stage=stage_name, **kwargs)
    stage_metrics: dict[str, Any] = {}
    try:
        yield stage_metrics
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        StructuredLogger.info(
            f"stage_completed:{stage_name}",
            stage=stage_name,
            duration_ms=duration_ms,
            status="success",
            **stage_metrics,
        )
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        StructuredLogger.error(
            f"stage_failed:{stage_name}",
            stage=stage_name,
            duration_ms=duration_ms,
            status="failed",
            error_summary=str(exc)[:200],
            **stage_metrics,
        )
        raise
