"""Error handling and retry policies for the orchestration pipeline.

Implements strategies for recovering from different types of failures,
with stage-specific retry logic and fallback mechanisms.
"""

import time
from enum import Enum
from typing import Any, Callable, TypeVar

from groww_pulse.logging_utils.logger import StructuredLogger

T = TypeVar("T")


class ErrorSeverity(Enum):
    """Severity classification for errors."""

    RETRIABLE = "retriable"  # Can retry with exponential backoff
    FALLBACK = "fallback"  # Can use fallback strategy
    BLOCKED = "blocked"  # Cannot recover, run must stop


class StageRetryPolicy:
    """Retry policy for a specific pipeline stage."""

    def __init__(
        self,
        stage_name: str,
        max_attempts: int = 1,
        initial_backoff_sec: float = 0.5,
        max_backoff_sec: float = 30.0,
        backoff_multiplier: float = 2.0,
        retriable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        """Initialize retry policy for a stage.

        Args:
            stage_name: Name of the pipeline stage
            max_attempts: Maximum number of retry attempts
            initial_backoff_sec: Initial backoff duration in seconds
            max_backoff_sec: Maximum backoff duration in seconds
            backoff_multiplier: Exponential backoff multiplier
            retriable_exceptions: Tuple of exception types to retry on
        """
        self.stage_name = stage_name
        self.max_attempts = max_attempts
        self.initial_backoff_sec = initial_backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self.backoff_multiplier = backoff_multiplier
        self.retriable_exceptions = retriable_exceptions

    def should_retry(self, exc: Exception, attempt: int) -> bool:
        """Determine if an exception should trigger a retry.

        Args:
            exc: Exception that occurred
            attempt: Current attempt number (0-indexed)

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_attempts:
            return False

        return isinstance(exc, self.retriable_exceptions)

    def get_backoff_duration(self, attempt: int) -> float:
        """Calculate backoff duration for exponential backoff.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Backoff duration in seconds
        """
        backoff = self.initial_backoff_sec * (self.backoff_multiplier ** attempt)
        return min(backoff, self.max_backoff_sec)

    def execute_with_retry(
        self, fn: Callable[[], T], run_id: str | None = None
    ) -> T:
        """Execute function with exponential backoff retry logic.

        Args:
            fn: Callable to execute
            run_id: Optional run ID for logging

        Returns:
            Result of function execution

        Raises:
            The last exception if all attempts fail
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc

                if not self.should_retry(exc, attempt):
                    # Non-retriable error or last attempt
                    StructuredLogger.error(
                        f"{self.stage_name}_non_retriable_error",
                        run_id=run_id or "unknown",
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:200],
                        attempt=attempt + 1,
                    )
                    raise

                # Calculate backoff and retry
                backoff = self.get_backoff_duration(attempt)
                StructuredLogger.warning(
                    f"{self.stage_name}_retry",
                    run_id=run_id or "unknown",
                    error_type=type(exc).__name__,
                    attempt=attempt + 1,
                    max_attempts=self.max_attempts,
                    backoff_sec=backoff,
                )
                time.sleep(backoff)

        # Should not reach here, but raise last exception if it does
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Unexpected failure in {self.stage_name} after all retries")


class PipelineErrorHandler:
    """Handles errors across all pipeline stages with appropriate recovery strategies."""

    def __init__(self) -> None:
        """Initialize error handler with stage-specific retry policies."""
        # Collection stage: retry on timeout/network errors
        self.collection_policy = StageRetryPolicy(
            stage_name="collection",
            max_attempts=3,
            initial_backoff_sec=1.0,
            retriable_exceptions=(TimeoutError, ConnectionError, IOError),
        )

        # Theme analysis: retry on LLM timeout/API errors
        self.analysis_policy = StageRetryPolicy(
            stage_name="theme_analysis",
            max_attempts=2,
            initial_backoff_sec=0.5,
            retriable_exceptions=(TimeoutError, RuntimeError),
        )

        # MCP delivery: retry on MCP service errors
        self.delivery_policy = StageRetryPolicy(
            stage_name="delivery",
            max_attempts=2,
            initial_backoff_sec=1.0,
            retriable_exceptions=(RuntimeError, IOError),
        )

        # Non-retriable stages (should fail immediately)
        self.privacy_policy = StageRetryPolicy(
            stage_name="privacy_filtering",
            max_attempts=1,
            retriable_exceptions=(),  # No retries - deterministic
        )

        self.validation_policy = StageRetryPolicy(
            stage_name="validation",
            max_attempts=1,
            retriable_exceptions=(),  # No retries - validation failure is final
        )

    def classify_error(self, stage_name: str, exc: Exception) -> ErrorSeverity:
        """Classify error severity for a given pipeline stage.

        Args:
            stage_name: Name of the pipeline stage
            exc: Exception that occurred

        Returns:
            ErrorSeverity classification
        """
        # Privacy filter and validation failures block the run
        if stage_name in ("privacy_filtering", "normalization_and_privacy", "pulse_validation"):
            if isinstance(exc, ValueError):
                return ErrorSeverity.BLOCKED

        # Collection and analysis errors can be retried
        if stage_name in ("collection", "theme_analysis"):
            if isinstance(exc, (TimeoutError, ConnectionError, IOError)):
                return ErrorSeverity.RETRIABLE

        # Delivery errors can be retried
        if stage_name == "delivery":
            if isinstance(exc, (RuntimeError, IOError)):
                return ErrorSeverity.RETRIABLE

        # Default to blocked for safety
        return ErrorSeverity.BLOCKED

    def get_recovery_suggestion(self, stage_name: str, exc: Exception) -> str:
        """Get recovery suggestion for a failed stage.

        Args:
            stage_name: Name of the pipeline stage
            exc: Exception that occurred

        Returns:
            Recovery suggestion message
        """
        exc_type = type(exc).__name__

        if stage_name == "collection":
            if "timeout" in str(exc).lower():
                return "Google Play API timeout. Retry with longer timeout or smaller review batch."
            if "quota" in str(exc).lower():
                return "Google Play API quota exceeded. Wait and retry after quota reset."
            return f"Collection failed ({exc_type}). Check network and API credentials."

        if stage_name == "theme_analysis":
            if "timeout" in str(exc).lower():
                return "LLM model timeout. Reduce batch_size or increase model_timeout_sec."
            if "rate" in str(exc).lower():
                return "LLM rate limit hit. Retry after backoff or use fallback classifier."
            return f"Theme analysis failed ({exc_type}). Check LLM configuration."

        if stage_name == "delivery":
            if "document" in str(exc).lower():
                return "Document operation failed. Verify existing_document_id is valid."
            if "authorization" in str(exc).lower():
                return "MCP authorization failed. Check credentials and MCP server status."
            return f"Delivery failed ({exc_type}). Verify MCP server is running."

        if stage_name in ("normalization_and_privacy", "pulse_validation"):
            return f"{stage_name} validation failed ({exc_type}). This run cannot proceed."

        return f"Pipeline stage {stage_name} failed ({exc_type}). Check logs for details."


# Global error handler instance
_error_handler = PipelineErrorHandler()


def get_error_handler() -> PipelineErrorHandler:
    """Get the global error handler instance.

    Returns:
        PipelineErrorHandler instance
    """
    return _error_handler
