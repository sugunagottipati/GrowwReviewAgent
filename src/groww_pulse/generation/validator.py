from collections.abc import Sequence

from groww_pulse.analysis.provenance import verify_quote_provenance
from groww_pulse.domain.models import Quote, WeeklyPulse
from groww_pulse.generation.base import PulseValidator
from groww_pulse.processing.privacy_filter import (
    ACCOUNT_CARD_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    URL_PARAM_PATTERN,
)


class StandardPulseValidator(PulseValidator):
    """Enforces strict structural, cardinality, provenance, privacy, and length constraints on weekly pulse."""

    def validate(
        self,
        pulse: WeeklyPulse,
        source_quotes: Sequence[Quote],
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []

        # 1. Cardinality checks
        if len(pulse.top_themes) != 3:
            errors.append(f"Expected exactly 3 themes, got {len(pulse.top_themes)}")
        if len(pulse.quotes) != 3:
            errors.append(f"Expected exactly 3 quotes, got {len(pulse.quotes)}")
        if len(pulse.actions) != 3:
            errors.append(f"Expected exactly 3 actions, got {len(pulse.actions)}")

        # 2. Section presence checks
        required_sections = [
            "# Groww Weekly Review Pulse",
            "## Top Themes",
            "## What Users Said",
            "## Recommended Actions",
        ]
        for section in required_sections:
            if section not in pulse.markdown:
                errors.append(f"Missing required section in markdown: '{section}'")

        # 3. Word count check (<= 250 words)
        if pulse.word_count > 250:
            errors.append(
                f"Pulse exceeds maximum word count of 250: current count is {pulse.word_count}"
            )

        # 4. Quote provenance check
        source_quotes_by_id = {quote.source_review_id: quote.text for quote in source_quotes}
        for q in pulse.quotes:
            source_text = source_quotes_by_id.get(q.source_review_id, "")
            if not verify_quote_provenance(q.text, source_text):
                errors.append(
                    f"Quote provenance violation: quote '{q.text[:30]}...' not found in source evidence."
                )

        # 5. PII absence check
        if EMAIL_PATTERN.search(pulse.markdown):
            errors.append("Privacy violation: Unredacted email pattern detected in pulse output.")
        if PHONE_PATTERN.search(pulse.markdown):
            errors.append("Privacy violation: Unredacted phone pattern detected in pulse output.")
        if ACCOUNT_CARD_PATTERN.search(pulse.markdown):
            errors.append("Privacy violation: Unredacted account or card pattern detected in pulse output.")
        if URL_PARAM_PATTERN.search(pulse.markdown):
            errors.append("Privacy violation: Personal URL parameters detected in pulse output.")

        return len(errors) == 0, errors
