import json
from datetime import datetime

import pytest

from groww_pulse.analysis.llm_theme_analyzer import (
    LangChainThemeAnalyzer,
    ThemeAnalysisUnavailableError,
)
from groww_pulse.config.settings import Settings
from groww_pulse.domain.models import Review
from groww_pulse.langchain_layer.model_factory import FakeStructuredChatModel


def _review(review_id: str, rating: int, text: str) -> Review:
    return Review(
        source_review_id=review_id,
        rating=rating,
        title=None,
        text=text,
        reviewed_at=datetime.now(),
        locale="en_IN",
        content_hash=f"hash_{review_id}",
    )


def _payload(label: str, review_ids: list[str], sentiment: str = "negative") -> str:
    return json.dumps(
        {
            "candidate_themes": [
                {
                    "label": label,
                    "review_ids": review_ids,
                    "sentiment": sentiment,
                    "summary": "s",
                    "action_rationale": "a",
                }
            ],
            "unassigned_review_ids": [],
        }
    )


class TestLangChainThemeAnalyzer:
    def test_analyzes_single_batch_and_consolidates(self) -> None:
        reviews = [_review("r1", 1, "UPI payment failed"), _review("r2", 2, "UPI deposit stuck")]
        fake_model = FakeStructuredChatModel(responses=[_payload("Payments", ["r1", "r2"])])
        settings = Settings(batch_size=10, timeout_seconds=5)
        analyzer = LangChainThemeAnalyzer(model=fake_model, settings=settings, max_workers=2)

        themes = analyzer.analyze_themes(reviews)

        assert len(themes) == 1
        assert themes[0].label == "Payments"
        assert set(themes[0].evidence_review_ids) == {"r1", "r2"}

    def test_batches_reviews_according_to_batch_size(self) -> None:
        reviews = [_review(f"r{i}", 1, f"review text number {i}") for i in range(4)]
        fake_model = FakeStructuredChatModel(
            responses=[
                _payload("ThemeA", ["r0", "r1"]),
                _payload("ThemeB", ["r2", "r3"]),
            ]
        )
        settings = Settings(batch_size=2, timeout_seconds=5)
        analyzer = LangChainThemeAnalyzer(model=fake_model, settings=settings, max_workers=2)

        themes = analyzer.analyze_themes(reviews)

        assert fake_model.call_count == 2
        assert {t.label for t in themes} == {"ThemeA", "ThemeB"}

    def test_empty_reviews_returns_no_themes(self) -> None:
        fake_model = FakeStructuredChatModel(responses=["{}"])
        analyzer = LangChainThemeAnalyzer(model=fake_model)

        assert analyzer.analyze_themes([]) == []

    def test_partial_batch_failure_still_consolidates_successful_batches(self) -> None:
        reviews = [_review(f"r{i}", 1, f"review text number {i}") for i in range(4)]

        class FlakyModel(FakeStructuredChatModel):
            def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
                base_runnable = super().with_structured_output(schema, **kwargs)

                def _flaky_invoke(input_val):
                    self.call_count += 1
                    if self.call_count == 1:
                        raise RuntimeError("simulated provider error")
                    return base_runnable.invoke(input_val)

                from langchain_core.runnables import RunnableLambda

                return RunnableLambda(_flaky_invoke)

        flaky = FlakyModel(responses=[_payload("ThemeB", ["r2", "r3"])])
        settings = Settings(batch_size=2, timeout_seconds=5)
        analyzer = LangChainThemeAnalyzer(model=flaky, settings=settings, max_workers=1)

        themes = analyzer.analyze_themes(reviews)

        assert len(themes) == 1
        assert themes[0].label == "ThemeB"

    def test_raises_when_all_batches_fail(self) -> None:
        class AlwaysFailsModel(FakeStructuredChatModel):
            def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
                from langchain_core.runnables import RunnableLambda

                def _fail(_input_val):
                    raise RuntimeError("provider outage")

                return RunnableLambda(_fail)

        reviews = [_review("r1", 1, "some review text")]
        settings = Settings(batch_size=10, timeout_seconds=5)
        analyzer = LangChainThemeAnalyzer(model=AlwaysFailsModel(), settings=settings)

        with pytest.raises(ThemeAnalysisUnavailableError):
            analyzer.analyze_themes(reviews)
