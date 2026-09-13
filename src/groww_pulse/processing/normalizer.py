import hashlib
import unicodedata
from collections.abc import Sequence

from groww_pulse.collection.models import RawReview
from groww_pulse.domain.models import Review
from groww_pulse.processing.base import ReviewNormalizer


class StandardReviewNormalizer(ReviewNormalizer):
    """Normalizes review text, whitespace, unicode, and generates stable content hashes."""

    def normalize(self, raw_reviews: Sequence[RawReview]) -> Sequence[Review]:
        normalized_reviews: list[Review] = []
        seen_ids: set[str] = set()

        for raw in raw_reviews:
            if not raw.review_id or raw.review_id in seen_ids:
                continue

            cleaned_text = self._normalize_text(raw.text)
            if not cleaned_text:
                continue

            cleaned_title = self._normalize_text(raw.title) if raw.title else None
            content_hash = self._generate_hash(raw.review_id, cleaned_text)

            normalized_reviews.append(
                Review(
                    source_review_id=raw.review_id,
                    rating=raw.rating,
                    title=cleaned_title,
                    text=cleaned_text,
                    reviewed_at=raw.reviewed_at,
                    locale=raw.locale or "en_IN",
                    source_url=raw.source_url,
                    content_hash=content_hash,
                )
            )
            seen_ids.add(raw.review_id)

        return normalized_reviews

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        # Unicode NFKC normalization
        normalized = unicodedata.normalize("NFKC", text)
        # Collapse multiple whitespace characters into a single space
        return " ".join(normalized.split()).strip()

    @staticmethod
    def _generate_hash(source_id: str, text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(source_id.encode("utf-8"))
        hasher.update(b":")
        hasher.update(text.encode("utf-8"))
        return hasher.hexdigest()
