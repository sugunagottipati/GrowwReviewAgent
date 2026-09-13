from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from groww_pulse.domain.models import Action, Quote, Theme, WeeklyPulse


class PulseComposer(ABC):
    """Interface for rendering validated weekly pulse content."""

    @abstractmethod
    def compose(
        self,
        week_ending: date,
        themes: Sequence[Theme],
        quotes: Sequence[Quote],
        actions: Sequence[Action],
    ) -> WeeklyPulse:
        """Compose the weekly pulse artifact."""
        ...


class PulseValidator(ABC):
    """Interface for enforcing pulse structure, provenance, privacy, and word count constraints."""

    @abstractmethod
    def validate(
        self,
        pulse: WeeklyPulse,
        source_quotes: Sequence[Quote],
    ) -> tuple[bool, list[str]]:
        """Validate pulse and return (is_valid, validation_errors)."""
        ...
