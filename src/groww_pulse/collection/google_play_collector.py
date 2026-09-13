import time
from collections.abc import Sequence
from datetime import date
from typing import Any

from google_play_scraper import Sort
from google_play_scraper import reviews as fetch_play_reviews

from groww_pulse.collection.base import ReviewCollector
from groww_pulse.collection.models import CollectionError, CollectionMetrics, RawReview


class GooglePlayReviewCollector(ReviewCollector):
    """Collects public Google Play Store reviews via the compliant `google-play-scraper` library.

    Paginates newest-first, tolerates unsorted pages by only halting once an entire page is
    confirmed older than the cutoff date, deduplicates by source review ID across pages, and
    retries transient provider errors with bounded exponential backoff.
    """

    def __init__(
        self,
        page_size: int = 200,
        max_pages: int = 50,
        max_retries: int = 3,
        initial_backoff_seconds: float = 1.0,
    ) -> None:
        super().__init__()
        self._page_size = page_size
        self._max_pages = max_pages
        self._max_retries = max_retries
        self._initial_backoff_seconds = initial_backoff_seconds

    def collect_reviews(
        self,
        app_id: str,
        cutoff_date: date,
        locale: str = "en_IN",
    ) -> Sequence[RawReview]:
        lang, country = self._parse_locale(locale)
        metrics = CollectionMetrics()
        seen_ids: set[str] = set()
        collected: list[RawReview] = []
        continuation_token = None
        page_count = 0

        while page_count < self._max_pages:
            try:
                page_results, continuation_token = self._fetch_page_with_retry(
                    app_id, lang, country, continuation_token, metrics
                )
            except CollectionError as exc:
                metrics.provider_errors.append(f"page_abandoned: {type(exc).__name__}")
                break

            page_count += 1
            metrics.pages_read = page_count
            metrics.records_received += len(page_results)

            if not page_results:
                break

            mapped = [
                raw
                for item in page_results
                if (raw := self._map_to_raw_review(item, app_id, locale)) is not None
            ]

            page_all_older = bool(mapped) and all(
                m.reviewed_at.date() < cutoff_date for m in mapped
            )

            for raw in mapped:
                if raw.review_id in seen_ids:
                    continue
                seen_ids.add(raw.review_id)
                if raw.reviewed_at.date() >= cutoff_date:
                    collected.append(raw)
                    metrics.records_in_window += 1

            if page_all_older or continuation_token is None:
                break

        self.last_metrics = metrics
        return collected

    def _fetch_page_with_retry(
        self,
        app_id: str,
        lang: str,
        country: str,
        continuation_token: Any,
        metrics: CollectionMetrics,
    ) -> tuple[list[dict[str, Any]], Any]:
        attempt = 0
        delay = self._initial_backoff_seconds
        last_exc: Exception | None = None

        while attempt <= self._max_retries:
            try:
                result, next_token = fetch_play_reviews(
                    app_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=self._page_size,
                    continuation_token=continuation_token,
                )
                return result, next_token
            except Exception as exc:
                last_exc = exc
                metrics.provider_errors.append(f"attempt_{attempt + 1}: {type(exc).__name__}")
                attempt += 1
                if attempt > self._max_retries:
                    break
                time.sleep(delay)
                delay *= 2

        raise CollectionError(
            f"Provider request failed after {self._max_retries + 1} attempts"
        ) from last_exc

    @staticmethod
    def _parse_locale(locale: str) -> tuple[str, str]:
        if "_" in locale:
            lang, country = locale.split("_", 1)
        else:
            lang, country = locale, "us"
        return lang.lower(), country.lower()

    @staticmethod
    def _map_to_raw_review(item: dict[str, Any], app_id: str, locale: str) -> RawReview | None:
        review_id = item.get("reviewId")
        content = item.get("content")
        score = item.get("score")
        reviewed_at = item.get("at")
        if not review_id or not content or score is None or reviewed_at is None:
            return None
        try:
            return RawReview(
                review_id=str(review_id),
                rating=int(score),
                title=None,
                text=str(content),
                reviewed_at=reviewed_at,
                locale=locale,
                source_url=f"https://play.google.com/store/apps/details?id={app_id}",
            )
        except ValueError:
            return None
