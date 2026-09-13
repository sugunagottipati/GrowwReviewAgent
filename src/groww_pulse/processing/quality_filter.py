from collections.abc import Sequence

from langdetect import DetectorFactory, LangDetectException, detect

from groww_pulse.domain.models import Review
from groww_pulse.processing.base import ReviewQualityFilter

# Deterministic language detection across runs
DetectorFactory.seed = 0

MIN_WORD_COUNT = 8
ENGLISH_LANGUAGE_CODE = "en"


class StandardReviewQualityFilter(ReviewQualityFilter):
    """Drops reviews shorter than the minimum word count or not written in English."""

    def filter(self, reviews: Sequence[Review]) -> tuple[Sequence[Review], int, int]:
        kept: list[Review] = []
        too_short_count = 0
        non_english_count = 0

        for review in reviews:
            if self._word_count(review.text) < MIN_WORD_COUNT:
                too_short_count += 1
                continue
            if not self._is_english(review.text):
                non_english_count += 1
                continue
            kept.append(review)

        return kept, too_short_count, non_english_count

    @staticmethod
    def _word_count(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _is_english(text: str) -> bool:
        try:
            return bool(detect(text) == ENGLISH_LANGUAGE_CODE)
        except LangDetectException:
            # Detector cannot extract reliable language features; treat as non-English.
            return False
