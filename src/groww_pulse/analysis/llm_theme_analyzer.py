from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from groww_pulse.analysis.base import ThemeAnalyzer
from groww_pulse.analysis.baseline import BaselineThemeAnalyzer
from groww_pulse.config.settings import Settings
from groww_pulse.domain.models import CandidateTheme, Review, Theme, ThemeAnalysis
from groww_pulse.langchain_layer.chains import create_analysis_chain
from groww_pulse.logging_utils.logger import StructuredLogger


class ThemeAnalysisUnavailableError(Exception):
    """Raised when every LangChain analysis batch fails, signaling callers to use the baseline fallback."""


def _chunk(items: Sequence[Review], size: int) -> list[list[Review]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _format_batch(batch: Sequence[Review]) -> str:
    """Render a batch of sanitized reviews as untrusted-data lines for the analysis prompt."""
    return "\n".join(f"[{r.source_review_id}] ({r.rating}\u2605) {r.text}" for r in batch)


class LangChainThemeAnalyzer(ThemeAnalyzer):
    """Invokes the LangChain analysis chain over sanitized review batches with bounded
    concurrency, per-batch timeouts, and provider-safe error handling. Candidate themes
    produced by the model are consolidated and scored by the deterministic baseline analyzer.
    """

    def __init__(
        self,
        model: BaseChatModel | None = None,
        settings: Settings | None = None,
        max_workers: int = 3,
        consolidator: ThemeAnalyzer | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._chain = create_analysis_chain(model=model)
        self._max_workers = max_workers
        self._consolidator = consolidator or BaselineThemeAnalyzer()

    def analyze_themes(
        self,
        reviews: Sequence[Review],
        candidates: ThemeAnalysis | None = None,
    ) -> Sequence[Theme]:
        if not reviews:
            return []

        batches = _chunk(reviews, self._settings.batch_size)
        merged_candidates: list[CandidateTheme] = []
        merged_unassigned: list[str] = []
        succeeded = 0

        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(batches))) as executor:
            futures: dict[Future[Any], int] = {
                executor.submit(self._invoke_batch, batch): idx
                for idx, batch in enumerate(batches)
            }
            pending = set(futures.keys())

            while pending:
                done, pending = wait(
                    pending, timeout=self._settings.timeout_seconds, return_when=FIRST_COMPLETED
                )
                if not done:
                    # No batch finished within the timeout window; abandon remaining batches.
                    for future in pending:
                        future.cancel()
                    StructuredLogger.warning(
                        "analysis_batch_timeout",
                        stage="theme_analysis",
                    )
                    break

                for future in done:
                    batch_index = futures[future]
                    try:
                        result = future.result()
                        merged_candidates.extend(result.candidate_themes)
                        merged_unassigned.extend(result.unassigned_review_ids)
                        succeeded += 1
                    except Exception as exc:
                        StructuredLogger.error(
                            "analysis_batch_failed",
                            stage="theme_analysis",
                            batch_index=batch_index,
                            error_summary=type(exc).__name__,
                        )

        if succeeded == 0:
            raise ThemeAnalysisUnavailableError(
                f"All {len(batches)} analysis batches failed; falling back to baseline analyzer"
            )

        merged = ThemeAnalysis(
            candidate_themes=merged_candidates,
            unassigned_review_ids=merged_unassigned,
        )
        return self._consolidator.analyze_themes(reviews, candidates=merged)

    def _invoke_batch(self, batch: Sequence[Review]) -> ThemeAnalysis:
        formatted = _format_batch(batch)
        result = self._chain.invoke({"formatted_reviews": formatted})
        if not isinstance(result, ThemeAnalysis):
            raise TypeError("Analysis chain returned non-ThemeAnalysis output")
        return result
