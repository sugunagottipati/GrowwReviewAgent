from datetime import date

import pytest

from groww_pulse.domain.enums import Sentiment
from groww_pulse.domain.models import Action, PulseDraft, Quote, Theme
from groww_pulse.generation.composer import StandardPulseComposer, count_stakeholder_words
from groww_pulse.generation.validator import StandardPulseValidator


def test_composer_and_validator_happy_path() -> None:
    composer = StandardPulseComposer()
    validator = StandardPulseValidator()

    themes = [
        Theme(
            id="t1",
            label="Payments and UPI",
            review_count=10,
            share_of_reviews=0.5,
            average_rating=2.0,
            sentiment=Sentiment.NEGATIVE,
            evidence_review_ids=["r1"],
        ),
        Theme(
            id="t2",
            label="KYC Verification",
            review_count=6,
            share_of_reviews=0.3,
            average_rating=2.5,
            sentiment=Sentiment.NEGATIVE,
            evidence_review_ids=["r2"],
        ),
        Theme(
            id="t3",
            label="App UI & Navigation",
            review_count=4,
            share_of_reviews=0.2,
            average_rating=4.5,
            sentiment=Sentiment.POSITIVE,
            evidence_review_ids=["r3"],
        ),
    ]

    quotes = [
        Quote(
            source_review_id="r1",
            text="UPI payment failed but money deducted",
            theme_id="t1",
            rating=1,
        ),
        Quote(
            source_review_id="r2", text="KYC document verification is slow", theme_id="t2", rating=2
        ),
        Quote(
            source_review_id="r3", text="App interface is clean and easy", theme_id="t3", rating=5
        ),
    ]

    actions = [
        Action(
            theme_id="t1", description="Improve UPI webhook handling to reduce deduction mismatch."
        ),
        Action(theme_id="t2", description="Add real-time status tracker for KYC submission steps."),
        Action(
            theme_id="t3", description="Maintain fast load times during peak market trading hours."
        ),
    ]

    pulse = composer.compose(
        week_ending=date(2026, 8, 30),
        themes=themes,
        quotes=quotes,
        actions=actions,
    )

    assert pulse.word_count <= 250
    assert "## Top Themes" in pulse.markdown
    assert "## What Users Said" in pulse.markdown
    assert "## Recommended Actions" in pulse.markdown

    is_valid, errors = validator.validate(pulse, source_quotes=quotes)
    assert is_valid is True
    assert len(errors) == 0


def test_validator_fails_on_unverified_quote() -> None:
    composer = StandardPulseComposer()
    validator = StandardPulseValidator()

    themes = [
        Theme(
            id="t1",
            label="T1",
            review_count=5,
            share_of_reviews=0.4,
            average_rating=2.0,
            sentiment=Sentiment.NEGATIVE,
            evidence_review_ids=["r1"],
        ),
        Theme(
            id="t2",
            label="T2",
            review_count=3,
            share_of_reviews=0.3,
            average_rating=3.0,
            sentiment=Sentiment.MIXED,
            evidence_review_ids=["r2"],
        ),
        Theme(
            id="t3",
            label="T3",
            review_count=2,
            share_of_reviews=0.3,
            average_rating=4.0,
            sentiment=Sentiment.POSITIVE,
            evidence_review_ids=["r3"],
        ),
    ]
    composed_quotes = [
        Quote(
            source_review_id="r1",
            text="Invented quote not in source evidence",
            theme_id="t1",
            rating=1,
        ),
        Quote(source_review_id="r2", text="Valid quote 2", theme_id="t2", rating=2),
        Quote(source_review_id="r3", text="Valid quote 3", theme_id="t3", rating=3),
    ]
    original_quotes = [
        Quote(source_review_id="r1", text="Original quote 1", theme_id="t1", rating=1),
        Quote(source_review_id="r2", text="Valid quote 2", theme_id="t2", rating=2),
        Quote(source_review_id="r3", text="Valid quote 3", theme_id="t3", rating=3),
    ]
    actions = [
        Action(theme_id="t1", description="Action 1"),
        Action(theme_id="t2", description="Action 2"),
        Action(theme_id="t3", description="Action 3"),
    ]

    pulse = composer.compose(
        week_ending=date(2026, 8, 30),
        themes=themes,
        quotes=composed_quotes,
        actions=actions,
    )

    is_valid, errors = validator.validate(pulse, source_quotes=original_quotes)
    assert is_valid is False
    assert any("Quote provenance violation" in err for err in errors)


def test_word_count_boundary() -> None:
    assert count_stakeholder_words("one two three") == 3
    # 250 words is accepted
    long_250_words = " ".join(["word"] * 250)
    assert count_stakeholder_words(long_250_words) == 250


def test_composer_renders_a_provenance_bound_model_draft() -> None:
    composer = StandardPulseComposer()
    themes = [
        Theme(id=f"t{index}", label=f"Theme {index}", review_count=3, share_of_reviews=0.33,
              average_rating=2.0, sentiment=Sentiment.NEGATIVE, evidence_review_ids=[f"r{index}"])
        for index in range(1, 4)
    ]
    quotes = [
        Quote(source_review_id=f"r{index}", text=f"The full sanitized review {index}.",
              theme_id=f"t{index}", rating=1)
        for index in range(1, 4)
    ]
    actions = [Action(theme_id=f"t{index}", description=f"Source action {index}") for index in range(1, 4)]
    draft = PulseDraft(
        themes=[{"theme_id": f"t{index}", "label": f"Theme {index}", "summary": f"Summary {index}"}
                for index in range(1, 4)],
        quotes=[{"source_review_id": f"r{index}", "quote_text": f"sanitized review {index}"}
                for index in range(1, 4)],
        actions=[{"theme_id": f"t{index}", "action_text": f"Draft action {index}"}
                 for index in range(1, 4)],
    )

    pulse = composer.compose_from_draft(date(2026, 8, 30), themes, quotes, actions, draft)

    assert '"sanitized review 1"' in pulse.markdown
    assert "Draft action 3" in pulse.markdown


def test_composer_rejects_model_quote_without_contiguous_provenance() -> None:
    composer = StandardPulseComposer()
    themes = [
        Theme(id=f"t{index}", label=f"Theme {index}", review_count=3, share_of_reviews=0.33,
              average_rating=2.0, sentiment=Sentiment.NEGATIVE, evidence_review_ids=[f"r{index}"])
        for index in range(1, 4)
    ]
    quotes = [Quote(source_review_id=f"r{index}", text=f"Source review {index}", theme_id=f"t{index}", rating=1)
              for index in range(1, 4)]
    actions = [Action(theme_id=f"t{index}", description=f"Action {index}") for index in range(1, 4)]
    draft = PulseDraft(
        themes=[{"theme_id": f"t{index}", "label": f"Theme {index}", "summary": "Summary"}
                for index in range(1, 4)],
        quotes=[{"source_review_id": "r1", "quote_text": "Invented"},
                {"source_review_id": "r2", "quote_text": "Source review 2"},
                {"source_review_id": "r3", "quote_text": "Source review 3"}],
        actions=[{"theme_id": f"t{index}", "action_text": f"Action {index}"} for index in range(1, 4)],
    )

    with pytest.raises(ValueError, match="contiguous source provenance"):
        composer.compose_from_draft(date(2026, 8, 30), themes, quotes, actions, draft)
