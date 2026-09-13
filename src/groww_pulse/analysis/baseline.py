import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from groww_pulse.analysis.base import ActionPlanner, QuoteSelector, ThemeAnalyzer
from groww_pulse.analysis.provenance import verify_quote_provenance
from groww_pulse.analysis.scoring import score_theme
from groww_pulse.domain.enums import Sentiment
from groww_pulse.domain.models import Action, Quote, Review, Theme, ThemeAnalysis

# Reviews within this window of the newest review count toward the recency score
_RECENCY_WINDOW_DAYS = 7


class BaselineThemeAnalyzer(ThemeAnalyzer):
    """Deterministic keyword-based theme analyzer for MVP, testing, and LangChain outage fallback."""

    THEME_KEYWORDS: dict[str, tuple[str, list[str]]] = {
        "payments": (
            "Payments and UPI",
            [
                "payment",
                "upi",
                "deposit",
                "withdrawal",
                "withdraw",
                "fund",
                "money",
                "bank",
                "transfer",
            ],
        ),
        "kyc": (
            "KYC and Account Verification",
            ["kyc", "verification", "document", "pan", "aadhaar", "otp", "verify", "account open"],
        ),
        "trading": (
            "Options Trading and Charting",
            [
                "chart",
                "option",
                "f&o",
                "trading",
                "order",
                "lag",
                "stoploss",
                "candlestick",
                "indicator",
            ],
        ),
        "ui": (
            "App Navigation and Usability",
            [
                "ui",
                "interface",
                "slow",
                "bug",
                "glitch",
                "crash",
                "navigation",
                "dark mode",
                "update",
            ],
        ),
        "charges": (
            "Brokerage and Charges",
            ["charge", "brokerage", "hidden", "fee", "cost", "tax", "gst", "pricing"],
        ),
    }

    def analyze_themes(
        self,
        reviews: Sequence[Review],
        candidates: ThemeAnalysis | None = None,
    ) -> Sequence[Theme]:
        if not reviews:
            return []

        review_map = {r.source_review_id: r for r in reviews}
        total_reviews = len(reviews)
        newest_reviewed_at = max(r.reviewed_at for r in reviews)
        recency_cutoff = newest_reviewed_at - timedelta(days=_RECENCY_WINDOW_DAYS)

        if candidates is not None and candidates.candidate_themes:
            buckets = self._consolidate_candidate_themes(candidates, review_map)
        else:
            buckets = self._bucket_by_keywords(reviews)

        scored_themes: list[tuple[float, Theme]] = []
        for theme_key, entry in buckets.items():
            review_ids = entry["review_ids"]
            label = entry["label"]
            declared_sentiment = entry.get("sentiment")

            matched_reviews = [review_map[rid] for rid in review_ids if rid in review_map]
            if not matched_reviews:
                continue

            review_count = len(matched_reviews)
            avg_rating = sum(r.rating for r in matched_reviews) / review_count
            low_rating_count = sum(1 for r in matched_reviews if r.rating <= 2)
            recency_count = sum(1 for r in matched_reviews if r.reviewed_at >= recency_cutoff)
            recency_fraction = recency_count / review_count

            sentiment = declared_sentiment or self._sentiment_from_rating(avg_rating)
            priority_score = score_theme(
                review_count=review_count,
                total_reviews=total_reviews,
                low_rating_count=low_rating_count,
                recency_fraction=recency_fraction,
                sentiment=sentiment,
            )

            scored_themes.append(
                (
                    priority_score,
                    Theme(
                        id=f"theme_{theme_key}_{uuid.uuid4().hex[:6]}",
                        label=label,
                        review_count=review_count,
                        share_of_reviews=round(review_count / total_reviews, 4),
                        average_rating=round(avg_rating, 2),
                        sentiment=sentiment,
                        evidence_review_ids=[rid for rid in review_ids if rid in review_map],
                    ),
                )
            )

        # Rank by priority score (volume, low-rating concentration, recency, sentiment); cap at 5.
        ranked = sorted(scored_themes, key=lambda pair: pair[0], reverse=True)[:5]
        return [theme for _, theme in ranked]

    def _bucket_by_keywords(self, reviews: Sequence[Review]) -> dict[str, dict[str, Any]]:
        """Deterministic keyword-based clustering used when no LangChain candidates are available."""
        theme_buckets: dict[str, list[str]] = defaultdict(list)

        for r in reviews:
            text_lower = (r.title + " " + r.text).lower() if r.title else r.text.lower()
            matched = False
            for theme_key, (_, keywords) in self.THEME_KEYWORDS.items():
                if any(kw in text_lower for kw in keywords):
                    theme_buckets[theme_key].append(r.source_review_id)
                    matched = True
                    break
            if not matched:
                theme_buckets["general"].append(r.source_review_id)

        return {
            theme_key: {
                "label": self.THEME_KEYWORDS.get(theme_key, (None,))[0] or "General User Experience",
                "review_ids": review_ids,
                "sentiment": None,
            }
            for theme_key, review_ids in theme_buckets.items()
            if review_ids
        }

    def _consolidate_candidate_themes(
        self,
        candidates: ThemeAnalysis,
        review_map: dict[str, Review],
    ) -> dict[str, dict[str, Any]]:
        """Merge LangChain candidate themes with synonymous/duplicate labels into final buckets."""
        merged: dict[str, dict[str, Any]] = {}
        sentiment_votes: dict[str, dict[Sentiment, int]] = defaultdict(lambda: defaultdict(int))

        for candidate in candidates.candidate_themes:
            normalized_key = self._normalize_label(candidate.label)
            valid_ids = [rid for rid in candidate.review_ids if rid in review_map]
            if not valid_ids:
                continue

            if normalized_key not in merged:
                merged[normalized_key] = {
                    "label": candidate.label.strip(),
                    "review_ids": [],
                    "sentiment": None,
                }

            existing_ids = set(merged[normalized_key]["review_ids"])
            for rid in valid_ids:
                if rid not in existing_ids:
                    merged[normalized_key]["review_ids"].append(rid)
                    existing_ids.add(rid)

            sentiment_votes[normalized_key][candidate.sentiment] += 1

        for normalized_key, votes in sentiment_votes.items():
            merged[normalized_key]["sentiment"] = max(votes.items(), key=lambda kv: kv[1])[0]

        return merged

    @staticmethod
    def _normalize_label(label: str) -> str:
        return " ".join(label.strip().lower().split())

    @staticmethod
    def _sentiment_from_rating(avg_rating: float) -> Sentiment:
        if avg_rating >= 3.8:
            return Sentiment.POSITIVE
        if avg_rating <= 2.2:
            return Sentiment.NEGATIVE
        return Sentiment.MIXED


class BaselineQuoteSelector(QuoteSelector):
    """Selects concise, verbatim, provenance-verified quotes matching themes with rating diversity."""

    # Preferred excerpt length range for conciseness; falls back to any available length if unmet.
    _CONCISE_MIN_LEN = 15
    _CONCISE_MAX_LEN = 200

    def select_quotes(
        self,
        themes: Sequence[Theme],
        reviews: Sequence[Review],
        target_count: int = 3,
    ) -> Sequence[Quote]:
        review_map = {r.source_review_id: r for r in reviews}
        selected_quotes: list[Quote] = []
        used_review_ids: set[str] = set()
        used_ratings: set[int] = set()

        for theme in themes[:target_count]:
            candidate_review = self._pick_candidate(theme, review_map, used_review_ids, used_ratings)
            if candidate_review is None:
                continue

            if not verify_quote_provenance(candidate_review.text, candidate_review.text):
                continue

            used_review_ids.add(candidate_review.source_review_id)
            used_ratings.add(candidate_review.rating)
            selected_quotes.append(
                Quote(
                    source_review_id=candidate_review.source_review_id,
                    text=candidate_review.text,
                    theme_id=theme.id,
                    rating=candidate_review.rating,
                )
            )

        return selected_quotes[:target_count]

    def _pick_candidate(
        self,
        theme: Theme,
        review_map: dict[str, Review],
        used_review_ids: set[str],
        used_ratings: set[int],
    ) -> Review | None:
        eligible = [
            review_map[rid]
            for rid in theme.evidence_review_ids
            if rid in review_map and rid not in used_review_ids
        ]
        if not eligible:
            return None

        concise = [r for r in eligible if self._CONCISE_MIN_LEN <= len(r.text) <= self._CONCISE_MAX_LEN]
        pool = concise or eligible

        # Prefer a rating not yet represented among selected quotes, for rating coverage.
        for r in pool:
            if r.rating not in used_ratings:
                return r
        return pool[0]


class BaselineActionPlanner(ActionPlanner):
    """Produces concrete, evidence-grounded actions tied to top themes."""

    def plan_actions(
        self,
        top_themes: Sequence[Theme],
        reviews: Sequence[Review],
    ) -> Sequence[Action]:
        actions: list[Action] = []
        for theme in top_themes[:3]:
            # Reject ungrounded actions: an action must cite evidence for its associated theme.
            if not theme.evidence_review_ids:
                continue
            actions.append(
                Action(
                    theme_id=theme.id,
                    description=f"Investigate and address reported friction in '{theme.label}' to improve user experience.",
                    rationale=f"Addresses feedback from {theme.review_count} reviews with average rating {theme.average_rating}.",
                    evidence_review_ids=list(theme.evidence_review_ids[:5]),
                )
            )
        return actions
