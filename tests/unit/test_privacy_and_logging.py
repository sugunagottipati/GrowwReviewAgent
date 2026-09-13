import logging
from datetime import datetime

import pytest

from groww_pulse.domain.models import Review
from groww_pulse.logging_utils.logger import (
    StructuredLogger,
    sanitize_log_dict,
)
from groww_pulse.processing.privacy_filter import DeterministicPrivacyFilter


def test_privacy_filter_redacts_pii() -> None:
    filter_ = DeterministicPrivacyFilter()
    reviews = [
        Review(
            source_review_id="r1",
            rating=1,
            title="Help needed user@groww.in",
            text="Contact me at test.user@example.com or phone +919876543210. Card 4532 1122 3344 5566, url: https://example.com/pay?user=123&token=abc",
            reviewed_at=datetime.now(),
            content_hash="hash1",
        )
    ]

    safe_reviews, redacted_count, dropped_count = filter_.sanitize(reviews)

    assert len(safe_reviews) == 1
    assert redacted_count == 1
    assert dropped_count == 0

    sanitized = safe_reviews[0]
    assert "user@groww.in" not in (sanitized.title or "")
    assert "[EMAIL_REDACTED]" in (sanitized.title or "")
    assert "test.user@example.com" not in sanitized.text
    assert "[EMAIL_REDACTED]" in sanitized.text
    assert "9876543210" not in sanitized.text
    assert "[PHONE_REDACTED]" in sanitized.text
    assert "4532" not in sanitized.text
    assert "[ACCOUNT_REDACTED]" in sanitized.text
    assert "token=abc" not in sanitized.text
    assert "[LINK_REDACTED]" in sanitized.text


def test_sanitize_log_dict_blocks_forbidden_keys() -> None:
    data = {
        "author": "John Doe",
        "author_name": "Jane",
        "email": "user@example.com",
        "raw_text": "Secret review text",
        "review_text": "More secret text",
        "run_id": "run_123",
        "status": "completed",
        "review_count": 45,
        "duration_ms": 120.5,
    }

    sanitized = sanitize_log_dict(data)

    assert "author" not in sanitized
    assert "author_name" not in sanitized
    assert "email" not in sanitized
    assert "raw_text" not in sanitized
    assert "review_text" not in sanitized

    assert sanitized["run_id"] == "run_123"
    assert sanitized["status"] == "completed"
    assert sanitized["review_count"] == 45
    assert sanitized["duration_ms"] == 120.5


def test_structured_logger_log_capture(caplog: pytest.LogCaptureFixture) -> None:
    StructuredLogger._logger = None  # Reset singleton to test fresh logger

    # groww_pulse logger disables propagation (by design, to avoid duplicate/unsanitized
    # output on the root logger), so attach caplog's handler directly to capture records.
    logging.getLogger("groww_pulse").addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger="groww_pulse")

    StructuredLogger.info(
        "test_event",
        run_id="run_abc",
        author="Unauthorized Reviewer",  # Forbidden
        raw_text="This should never appear in logs",  # Forbidden
        review_count=10,  # Allowed
    )

    log_output = caplog.text
    assert "Unauthorized Reviewer" not in log_output
    assert "This should never appear in logs" not in log_output
    assert "run_abc" in log_output
    assert "review_count" in log_output
