import re
from collections.abc import Sequence

from groww_pulse.domain.models import Review
from groww_pulse.processing.base import PrivacyFilter

# Regex patterns for deterministic PII redaction
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?:\+?91[-.\s]?)?[6-9]\d{9}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
ACCOUNT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){12,19}\b")
URL_PARAM_PATTERN = re.compile(r"https?://\S+(?:\?[^\s]+)")


class DeterministicPrivacyFilter(PrivacyFilter):
    """Redacts PII (emails, phone numbers, account numbers, parameterized URLs) and drops unsafe text."""

    def sanitize(self, reviews: Sequence[Review]) -> tuple[Sequence[Review], int, int]:
        sanitized_reviews: list[Review] = []
        redacted_count = 0
        dropped_count = 0

        for r in reviews:
            redacted_text, is_redacted = self._redact_text(r.text)
            redacted_title, title_redacted = (
                self._redact_text(r.title) if r.title else (None, False)
            )

            if is_redacted or title_redacted:
                redacted_count += 1

            if not redacted_text.strip():
                dropped_count += 1
                continue

            sanitized_review = Review(
                source_review_id=r.source_review_id,
                rating=r.rating,
                title=redacted_title,
                text=redacted_text,
                reviewed_at=r.reviewed_at,
                locale=r.locale,
                source_url=r.source_url,
                content_hash=r.content_hash,
            )
            sanitized_reviews.append(sanitized_review)

        return sanitized_reviews, redacted_count, dropped_count

    def _redact_text(self, text: str) -> tuple[str, bool]:
        if not text:
            return "", False

        original = text
        text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
        text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
        text = ACCOUNT_CARD_PATTERN.sub("[ACCOUNT_REDACTED]", text)
        text = URL_PARAM_PATTERN.sub("[LINK_REDACTED]", text)

        was_redacted = original != text
        return text, was_redacted
