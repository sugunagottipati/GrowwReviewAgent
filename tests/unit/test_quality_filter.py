from datetime import datetime

from groww_pulse.domain.models import Review
from groww_pulse.processing.quality_filter import StandardReviewQualityFilter


def _review(review_id: str, text: str) -> Review:
    return Review(
        source_review_id=review_id,
        rating=3,
        title=None,
        text=text,
        reviewed_at=datetime.now(),
        locale="en_IN",
        content_hash=f"hash_{review_id}",
    )


def test_drops_reviews_shorter_than_eight_words() -> None:
    filter_ = StandardReviewQualityFilter()
    reviews = [
        _review("short", "Nice app good"),
        _review(
            "long_enough",
            "This application works really well for my daily stock market investing needs",
        ),
    ]

    kept, too_short_count, non_english_count = filter_.filter(reviews)

    assert [r.source_review_id for r in kept] == ["long_enough"]
    assert too_short_count == 1
    assert non_english_count == 0


def test_drops_non_english_reviews() -> None:
    filter_ = StandardReviewQualityFilter()
    reviews = [
        _review(
            "hindi",
            "यह ऐप बहुत अच्छा है और इसका उपयोग करना बहुत आसान है और तेज़ भी है",
        ),
        _review(
            "english",
            "This application works really well for my daily stock market investing needs",
        ),
    ]

    kept, too_short_count, non_english_count = filter_.filter(reviews)

    assert [r.source_review_id for r in kept] == ["english"]
    assert non_english_count == 1


def test_keeps_reviews_meeting_both_criteria() -> None:
    filter_ = StandardReviewQualityFilter()
    reviews = [
        _review(
            "good1",
            "Excellent trading platform with smooth order execution and great charts",
        ),
        _review(
            "good2",
            "Customer support resolved my KYC issue quickly and the app is reliable",
        ),
    ]

    kept, too_short_count, non_english_count = filter_.filter(reviews)

    assert len(kept) == 2
    assert too_short_count == 0
    assert non_english_count == 0
