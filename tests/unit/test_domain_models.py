from datetime import date, datetime

import pytest
from pydantic import ValidationError

from groww_pulse.domain.enums import RunStatus, Sentiment
from groww_pulse.domain.models import (
    Action,
    ActionDraft,
    CandidateTheme,
    PulseDraft,
    Quote,
    QuoteDraft,
    Review,
    Run,
    Theme,
    ThemeAnalysis,
    ThemeSummaryDraft,
)


def test_review_model_valid() -> None:
    rev = Review(
        source_review_id="rev_123",
        rating=5,
        title="Great app",
        text="Very smooth mutual fund investments",
        reviewed_at=datetime(2026, 8, 15, 10, 0, 0),
        locale="en_IN",
        source_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        content_hash="abc123hash",
    )
    assert rev.source_review_id == "rev_123"
    assert rev.rating == 5
    assert rev.text == "Very smooth mutual fund investments"


def test_review_model_invalid_rating() -> None:
    with pytest.raises(ValidationError):
        Review(
            source_review_id="rev_123",
            rating=6,  # Rating must be between 1 and 5
            text="Invalid rating review",
            reviewed_at=datetime.now(),
            content_hash="hash",
        )


def test_theme_model_valid() -> None:
    theme = Theme(
        id="theme_01",
        label="Payments and UPI",
        review_count=15,
        share_of_reviews=0.35,
        average_rating=2.1,
        sentiment=Sentiment.NEGATIVE,
        evidence_review_ids=["rev_1", "rev_2"],
    )
    assert theme.label == "Payments and UPI"
    assert theme.sentiment == Sentiment.NEGATIVE


def test_quote_and_action_models() -> None:
    quote = Quote(
        source_review_id="rev_1",
        text="UPI deposit failed and money deducted",
        theme_id="theme_01",
        rating=1,
    )
    action = Action(
        theme_id="theme_01",
        description="Fix UPI bank callback latency to prevent false failure notices.",
        rationale="Top user pain point in 15 reviews.",
        evidence_review_ids=["rev_1"],
    )
    assert quote.source_review_id == "rev_1"
    assert action.theme_id == "theme_01"


def test_theme_analysis_model() -> None:
    analysis = ThemeAnalysis(
        candidate_themes=[
            CandidateTheme(
                label="Payments and UPI",
                review_ids=["rev_1", "rev_2"],
                sentiment=Sentiment.NEGATIVE,
                summary="Users reporting UPI deposit failures and bank deduction delays.",
                action_rationale="High volume of 1-star reviews regarding payment timeouts.",
            )
        ],
        unassigned_review_ids=["rev_3"],
    )
    assert len(analysis.candidate_themes) == 1
    assert analysis.candidate_themes[0].label == "Payments and UPI"


def test_pulse_draft_and_weekly_pulse() -> None:
    draft = PulseDraft(
        themes=[
            ThemeSummaryDraft(theme_id="t1", label="Payments", summary="Payment summary"),
            ThemeSummaryDraft(theme_id="t2", label="KYC", summary="KYC summary"),
            ThemeSummaryDraft(theme_id="t3", label="Trading", summary="Trading summary"),
        ],
        quotes=[
            QuoteDraft(source_review_id="r1", quote_text="Quote 1"),
            QuoteDraft(source_review_id="r2", quote_text="Quote 2"),
            QuoteDraft(source_review_id="r3", quote_text="Quote 3"),
        ],
        actions=[
            ActionDraft(theme_id="t1", action_text="Action 1"),
            ActionDraft(theme_id="t2", action_text="Action 2"),
            ActionDraft(theme_id="t3", action_text="Action 3"),
        ],
    )
    assert len(draft.themes) == 3
    assert len(draft.quotes) == 3
    assert len(draft.actions) == 3


def test_run_model() -> None:
    run = Run(
        id="run_test_123",
        started_at=datetime.now(),
        cutoff_date=date(2026, 6, 1),
        status=RunStatus.RUNNING,
        review_count=100,
    )
    assert run.status == RunStatus.RUNNING
    assert run.cutoff_date == date(2026, 6, 1)
