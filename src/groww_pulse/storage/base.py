from abc import ABC, abstractmethod
from collections.abc import Sequence

from groww_pulse.domain.models import Review, Run


class ReviewRepository(ABC):
    """Interface for storing and querying sanitized reviews."""

    @abstractmethod
    def save_reviews(self, reviews: Sequence[Review]) -> int:
        """Persist safe reviews idempotently and return the count of newly stored records."""
        ...

    @abstractmethod
    def get_reviews(self, limit: int = 1000) -> Sequence[Review]:
        """Retrieve stored sanitized reviews."""
        ...


class RunRepository(ABC):
    """Interface for tracking pipeline run states and delivery IDs."""

    @abstractmethod
    def create_run(self, run: Run) -> None:
        """Create a new run record."""
        ...

    @abstractmethod
    def update_run(self, run: Run) -> None:
        """Update an existing run record."""
        ...

    @abstractmethod
    def get_run(self, run_id: str) -> Run | None:
        """Fetch run record by ID."""
        ...

    @abstractmethod
    def list_runs(self, limit: int = 50) -> Sequence[Run]:
        """List historical run records."""
        ...
