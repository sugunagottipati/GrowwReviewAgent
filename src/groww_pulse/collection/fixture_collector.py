from collections.abc import Sequence
from datetime import date

from groww_pulse.collection.base import ReviewCollector
from groww_pulse.collection.models import CollectionMetrics, RawReview


class FixtureReviewCollector(ReviewCollector):
    """Fixture-backed review collector for offline development, dry runs, and tests."""

    def __init__(self, fixtures: Sequence[RawReview] | None = None) -> None:
        super().__init__()
        self._fixtures = list(fixtures) if fixtures is not None else []

    def set_fixtures(self, fixtures: Sequence[RawReview]) -> None:
        self._fixtures = list(fixtures)

    def collect_reviews(
        self,
        app_id: str,
        cutoff_date: date,
        locale: str = "en_IN",
    ) -> Sequence[RawReview]:
        seen_ids: set[str] = set()
        in_window: list[RawReview] = []
        for r in self._fixtures:
            if r.review_id in seen_ids:
                continue
            seen_ids.add(r.review_id)
            if r.reviewed_at.date() >= cutoff_date and (r.locale is None or r.locale == locale):
                in_window.append(r)

        self.last_metrics = CollectionMetrics(
            pages_read=1 if self._fixtures else 0,
            records_received=len(self._fixtures),
            records_in_window=len(in_window),
            provider_errors=[],
        )
        return in_window
