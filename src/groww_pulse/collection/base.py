from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from groww_pulse.collection.models import CollectionMetrics, RawReview


class ReviewCollector(ABC):
    """Abstract interface for public review collection."""

    def __init__(self) -> None:
        self.last_metrics: CollectionMetrics = CollectionMetrics()

    @abstractmethod
    def collect_reviews(
        self,
        app_id: str,
        cutoff_date: date,
        locale: str = "en_IN",
    ) -> Sequence[RawReview]:
        """Collect public reviews up to the cutoff date."""
        ...
