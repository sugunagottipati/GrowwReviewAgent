from abc import ABC, abstractmethod
from collections.abc import Sequence

from groww_pulse.domain.models import Action, Quote, Review, Theme, ThemeAnalysis


class ThemeAnalyzer(ABC):
    """Interface for consolidating and ranking themes from reviews and AI candidate themes."""

    @abstractmethod
    def analyze_themes(
        self,
        reviews: Sequence[Review],
        candidates: ThemeAnalysis | None = None,
    ) -> Sequence[Theme]:
        """Produce up to 5 ranked themes with supporting review IDs."""
        ...


class QuoteSelector(ABC):
    """Interface for selecting representative, verbatim quotes from ranked themes and safe reviews."""

    @abstractmethod
    def select_quotes(
        self,
        themes: Sequence[Theme],
        reviews: Sequence[Review],
        target_count: int = 3,
    ) -> Sequence[Quote]:
        """Select verbatim quotes matching theme provenance."""
        ...


class ActionPlanner(ABC):
    """Interface for generating concrete actions tied to top themes."""

    @abstractmethod
    def plan_actions(
        self,
        top_themes: Sequence[Theme],
        reviews: Sequence[Review],
    ) -> Sequence[Action]:
        """Generate one grounded action per top theme."""
        ...
