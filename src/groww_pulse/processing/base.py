from abc import ABC, abstractmethod
from collections.abc import Sequence

from groww_pulse.collection.models import RawReview
from groww_pulse.domain.models import Review


class ReviewNormalizer(ABC):
    """Interface for review text and metadata normalization."""

    @abstractmethod
    def normalize(self, raw_reviews: Sequence[RawReview]) -> Sequence[Review]:
        """Normalize raw reviews into structured safe reviews."""
        ...


class PrivacyFilter(ABC):
    """Interface for PII redaction and author field removal."""

    @abstractmethod
    def sanitize(self, reviews: Sequence[Review]) -> tuple[Sequence[Review], int, int]:
        """Sanitize reviews and return (safe_reviews, redacted_count, dropped_count)."""
        ...


class ReviewQualityFilter(ABC):
    """Interface for content-quality filtering: minimum length and English-language enforcement."""

    @abstractmethod
    def filter(self, reviews: Sequence[Review]) -> tuple[Sequence[Review], int, int]:
        """Filter reviews and return (kept_reviews, too_short_count, non_english_count)."""
        ...
