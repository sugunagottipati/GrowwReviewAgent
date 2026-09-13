from collections.abc import Sequence

from groww_pulse.domain.models import Review, Run
from groww_pulse.storage.base import ReviewRepository, RunRepository


class InMemoryRepository(ReviewRepository, RunRepository):
    """In-memory repository for isolated unit testing and dry runs."""

    def __init__(self) -> None:
        self._reviews: dict[str, Review] = {}
        self._runs: dict[str, Run] = {}

    def save_reviews(self, reviews: Sequence[Review]) -> int:
        inserted = 0
        for r in reviews:
            if r.source_review_id not in self._reviews:
                self._reviews[r.source_review_id] = r
                inserted += 1
        return inserted

    def get_reviews(self, limit: int = 1000) -> Sequence[Review]:
        return list(self._reviews.values())[:limit]

    def create_run(self, run: Run) -> None:
        self._runs[run.id] = run

    def update_run(self, run: Run) -> None:
        self._runs[run.id] = run

    def get_run(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list_runs(self, limit: int = 50) -> Sequence[Run]:
        return list(self._runs.values())[:limit]
