from datetime import datetime, timedelta

from groww_pulse.analysis.baseline import (
    BaselineActionPlanner,
    BaselineQuoteSelector,
    BaselineThemeAnalyzer,
)
from groww_pulse.analysis.provenance import verify_quote_provenance
from groww_pulse.analysis.scoring import score_theme
from groww_pulse.domain.enums import Sentiment
from groww_pulse.domain.models import CandidateTheme, Review, Theme, ThemeAnalysis


def _review(review_id: str, rating: int, text: str, days_ago: int = 0) -> Review:
    return Review(
        source_review_id=review_id,
        rating=rating,
        title=None,
        text=text,
        reviewed_at=datetime.now() - timedelta(days=days_ago),
        locale="en_IN",
        content_hash=f"hash_{review_id}",
    )


class TestVerifyQuoteProvenance:
    def test_accepts_exact_substring(self) -> None:
        assert verify_quote_provenance("UPI payment failed", "The UPI payment failed today") is True

    def test_rejects_non_substring(self) -> None:
        assert verify_quote_provenance("invented quote", "totally different review text") is False

    def test_rejects_empty_inputs(self) -> None:
        assert verify_quote_provenance("", "some text") is False
        assert verify_quote_provenance("some quote", "") is False


class TestScoreTheme:
    def test_higher_volume_and_low_rating_scores_higher(self) -> None:
        high = score_theme(
            review_count=8, total_reviews=10, low_rating_count=6, recency_fraction=0.5,
            sentiment=Sentiment.NEGATIVE,
        )
        low = score_theme(
            review_count=1, total_reviews=10, low_rating_count=0, recency_fraction=0.0,
            sentiment=Sentiment.POSITIVE,
        )
        assert high > low

    def test_zero_reviews_scores_zero(self) -> None:
        assert score_theme(0, 10, 0, 0.0, Sentiment.MIXED) == 0.0


class TestBaselineThemeAnalyzerKeywordFallback:
    def test_produces_at_most_five_themes(self) -> None:
        reviews = [
            _review("r1", 1, "UPI payment deposit failed badly"),
            _review("r2", 2, "KYC verification document pending review"),
            _review("r3", 1, "Options trading chart lag during market open"),
            _review("r4", 5, "App interface navigation is clean and simple"),
            _review("r5", 1, "Brokerage charges and hidden fee are unclear"),
            _review("r6", 3, "Something entirely unrelated to any keyword bucket"),
        ]
        analyzer = BaselineThemeAnalyzer()

        themes = analyzer.analyze_themes(reviews)

        assert len(themes) <= 5
        assert all(t.evidence_review_ids for t in themes)

    def test_empty_reviews_returns_no_themes(self) -> None:
        assert BaselineThemeAnalyzer().analyze_themes([]) == []


class TestBaselineThemeAnalyzerCandidateConsolidation:
    def test_merges_synonymous_labels_case_insensitively(self) -> None:
        reviews = [
            _review("r1", 1, "UPI deposit failed"),
            _review("r2", 1, "UPI withdrawal also failed"),
            _review("r3", 2, "Payment gateway timeout"),
        ]
        candidates = ThemeAnalysis(
            candidate_themes=[
                CandidateTheme(
                    label="Payments and UPI",
                    review_ids=["r1", "r2"],
                    sentiment=Sentiment.NEGATIVE,
                    summary="UPI failures",
                    action_rationale="Fix UPI gateway",
                ),
                CandidateTheme(
                    label="  payments and upi  ",
                    review_ids=["r3"],
                    sentiment=Sentiment.NEGATIVE,
                    summary="Gateway timeout",
                    action_rationale="Fix gateway timeout",
                ),
            ],
            unassigned_review_ids=[],
        )
        analyzer = BaselineThemeAnalyzer()

        themes = analyzer.analyze_themes(reviews, candidates=candidates)

        assert len(themes) == 1
        assert themes[0].review_count == 3
        assert set(themes[0].evidence_review_ids) == {"r1", "r2", "r3"}

    def test_drops_candidate_themes_with_no_matching_reviews(self) -> None:
        reviews = [_review("r1", 1, "UPI deposit failed")]
        candidates = ThemeAnalysis(
            candidate_themes=[
                CandidateTheme(
                    label="Payments",
                    review_ids=["r1"],
                    sentiment=Sentiment.NEGATIVE,
                    summary="s",
                    action_rationale="a",
                ),
                CandidateTheme(
                    label="Ghost Theme",
                    review_ids=["nonexistent"],
                    sentiment=Sentiment.MIXED,
                    summary="s",
                    action_rationale="a",
                ),
            ],
            unassigned_review_ids=[],
        )

        themes = BaselineThemeAnalyzer().analyze_themes(reviews, candidates=candidates)

        assert len(themes) == 1
        assert themes[0].label == "Payments"

    def test_ranks_by_score_not_just_review_count(self) -> None:
        # Small theme: 1 review, rating 1 (negative, low-rating) vs large theme: 3 reviews, rating 5 (positive)
        reviews = [
            _review("r1", 1, "Critical payment bug"),
            _review("r2", 5, "Great app"),
            _review("r3", 5, "Great app again"),
            _review("r4", 5, "Great app once more"),
        ]
        candidates = ThemeAnalysis(
            candidate_themes=[
                CandidateTheme(
                    label="Payments",
                    review_ids=["r1"],
                    sentiment=Sentiment.NEGATIVE,
                    summary="s",
                    action_rationale="a",
                ),
                CandidateTheme(
                    label="General",
                    review_ids=["r2", "r3", "r4"],
                    sentiment=Sentiment.POSITIVE,
                    summary="s",
                    action_rationale="a",
                ),
            ],
            unassigned_review_ids=[],
        )

        themes = BaselineThemeAnalyzer().analyze_themes(reviews, candidates=candidates)

        assert themes[0].label == "Payments"


class TestBaselineQuoteSelector:
    def test_selects_provenance_verified_quotes_with_rating_diversity(self) -> None:
        reviews = [
            _review("r1", 1, "Payment failed during checkout process today"),
            _review("r2", 5, "Great trading experience with fast charts"),
        ]
        themes = [
            Theme(
                id="t1",
                label="Payments",
                review_count=1,
                share_of_reviews=0.5,
                average_rating=1.0,
                sentiment=Sentiment.NEGATIVE,
                evidence_review_ids=["r1"],
            ),
            Theme(
                id="t2",
                label="Trading",
                review_count=1,
                share_of_reviews=0.5,
                average_rating=5.0,
                sentiment=Sentiment.POSITIVE,
                evidence_review_ids=["r2"],
            ),
        ]

        quotes = BaselineQuoteSelector().select_quotes(themes, reviews, target_count=2)

        assert len(quotes) == 2
        for quote in quotes:
            source_review = next(r for r in reviews if r.source_review_id == quote.source_review_id)
            assert verify_quote_provenance(quote.text, source_review.text)

    def test_does_not_reuse_same_review_across_themes(self) -> None:
        reviews = [_review("r1", 3, "Shared review text used only once")]
        themes = [
            Theme(
                id="t1", label="A", review_count=1, share_of_reviews=1.0, average_rating=3.0,
                sentiment=Sentiment.MIXED, evidence_review_ids=["r1"],
            ),
            Theme(
                id="t2", label="B", review_count=1, share_of_reviews=1.0, average_rating=3.0,
                sentiment=Sentiment.MIXED, evidence_review_ids=["r1"],
            ),
        ]

        quotes = BaselineQuoteSelector().select_quotes(themes, reviews, target_count=2)

        assert len(quotes) == 1


class TestBaselineActionPlanner:
    def test_generates_one_action_per_theme(self) -> None:
        themes = [
            Theme(
                id="t1", label="Payments", review_count=5, share_of_reviews=0.5,
                average_rating=2.0, sentiment=Sentiment.NEGATIVE,
                evidence_review_ids=["r1", "r2"],
            ),
        ]

        actions = BaselineActionPlanner().plan_actions(themes, [])

        assert len(actions) == 1
        assert actions[0].theme_id == "t1"
        assert actions[0].evidence_review_ids

    def test_rejects_ungrounded_actions_without_evidence(self) -> None:
        themes = [
            Theme(
                id="t1", label="Payments", review_count=0, share_of_reviews=0.0,
                average_rating=3.0, sentiment=Sentiment.MIXED, evidence_review_ids=[],
            ),
        ]

        actions = BaselineActionPlanner().plan_actions(themes, [])

        assert actions == []
