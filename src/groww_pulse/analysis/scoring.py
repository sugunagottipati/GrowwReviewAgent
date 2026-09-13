from groww_pulse.domain.enums import Sentiment

_SENTIMENT_WEIGHT: dict[Sentiment, float] = {
    Sentiment.NEGATIVE: 1.0,
    Sentiment.MIXED: 0.6,
    Sentiment.POSITIVE: 0.3,
}

# Relative weights for theme priority scoring (volume, low-rating concentration, recency, sentiment)
_VOLUME_WEIGHT = 0.40
_LOW_RATING_WEIGHT = 0.35
_RECENCY_WEIGHT = 0.15
_SENTIMENT_SCORE_WEIGHT = 0.10


def score_theme(
    review_count: int,
    total_reviews: int,
    low_rating_count: int,
    recency_fraction: float,
    sentiment: Sentiment,
) -> float:
    """Score a theme's priority using volume, low-rating concentration, recency, and sentiment."""
    if total_reviews <= 0 or review_count <= 0:
        return 0.0

    volume = review_count / total_reviews
    low_rating_ratio = low_rating_count / review_count
    sentiment_weight = _SENTIMENT_WEIGHT.get(sentiment, 0.5)

    return (
        _VOLUME_WEIGHT * volume
        + _LOW_RATING_WEIGHT * low_rating_ratio
        + _RECENCY_WEIGHT * recency_fraction
        + _SENTIMENT_SCORE_WEIGHT * sentiment_weight
    )
