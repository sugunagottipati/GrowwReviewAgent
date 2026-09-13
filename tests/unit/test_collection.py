from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from groww_pulse.collection.fixture_collector import FixtureReviewCollector
from groww_pulse.collection.google_play_collector import GooglePlayReviewCollector
from groww_pulse.collection.models import CollectionError, RawReview


def _raw_review(review_id: str, days_ago: int, locale: str = "en_IN") -> RawReview:
    return RawReview(
        review_id=review_id,
        rating=3,
        title=None,
        text=f"Review body {review_id}",
        reviewed_at=datetime.now() - timedelta(days=days_ago),
        locale=locale,
        source_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww",
    )


def _provider_item(review_id: str, when: datetime, score: int = 3, content: str = "text") -> dict[str, Any]:
    return {"reviewId": review_id, "content": content, "score": score, "at": when}


class TestFixtureReviewCollector:
    def test_excludes_reviews_outside_date_window(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        collector = FixtureReviewCollector(
            fixtures=[_raw_review("in_window", days_ago=1), _raw_review("out_of_window", days_ago=100)]
        )

        result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert [r.review_id for r in result] == ["in_window"]
        assert collector.last_metrics.records_received == 2
        assert collector.last_metrics.records_in_window == 1

    def test_deduplicates_by_review_id(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        dup = _raw_review("dup", days_ago=1)
        collector = FixtureReviewCollector(fixtures=[dup, dup])

        result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert len(result) == 1

    def test_filters_by_locale(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        collector = FixtureReviewCollector(
            fixtures=[_raw_review("en", days_ago=1, locale="en_IN"), _raw_review("hi", days_ago=1, locale="hi_IN")]
        )

        result = collector.collect_reviews(
            app_id="com.nextbillion.groww", cutoff_date=cutoff, locale="en_IN"
        )

        assert [r.review_id for r in result] == ["en"]


class TestGooglePlayReviewCollector:
    def test_stops_pagination_when_full_page_older_than_cutoff(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        newest_page = [
            _provider_item("r1", datetime.now() - timedelta(days=1)),
            _provider_item("r2", datetime.now() - timedelta(days=2)),
        ]
        old_page = [
            _provider_item("r3", datetime.now() - timedelta(weeks=10)),
            _provider_item("r4", datetime.now() - timedelta(weeks=12)),
        ]

        with patch(
            "groww_pulse.collection.google_play_collector.fetch_play_reviews",
            side_effect=[(newest_page, "token1"), (old_page, "token2")],
        ) as mocked:
            collector = GooglePlayReviewCollector()
            result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert [r.review_id for r in result] == ["r1", "r2"]
        assert mocked.call_count == 2
        assert collector.last_metrics.pages_read == 2
        assert collector.last_metrics.records_received == 4
        assert collector.last_metrics.records_in_window == 2

    def test_continues_through_unsorted_page_with_mixed_dates(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        mixed_page = [
            _provider_item("r1", datetime.now() - timedelta(days=1)),
            _provider_item("r2", datetime.now() - timedelta(weeks=10)),
        ]
        final_page = [_provider_item("r3", datetime.now() - timedelta(days=2))]

        with patch(
            "groww_pulse.collection.google_play_collector.fetch_play_reviews",
            side_effect=[(mixed_page, "token1"), (final_page, None)],
        ) as mocked:
            collector = GooglePlayReviewCollector()
            result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert mocked.call_count == 2
        assert {r.review_id for r in result} == {"r1", "r3"}

    def test_deduplicates_across_pages(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        page1 = [_provider_item("r1", datetime.now() - timedelta(days=1))]
        page2 = [
            _provider_item("r1", datetime.now() - timedelta(days=1)),
            _provider_item("r2", datetime.now() - timedelta(days=2)),
        ]

        with patch(
            "groww_pulse.collection.google_play_collector.fetch_play_reviews",
            side_effect=[(page1, "token1"), (page2, None)],
        ):
            collector = GooglePlayReviewCollector()
            result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert sorted(r.review_id for r in result) == ["r1", "r2"]

    def test_tolerates_missing_optional_fields(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        page = [
            _provider_item("r1", datetime.now() - timedelta(days=1)),
            {"reviewId": "r2", "content": None, "score": 3, "at": datetime.now()},
            {"reviewId": None, "content": "text", "score": 3, "at": datetime.now()},
        ]

        with patch(
            "groww_pulse.collection.google_play_collector.fetch_play_reviews",
            return_value=(page, None),
        ):
            collector = GooglePlayReviewCollector()
            result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert [r.review_id for r in result] == ["r1"]

    def test_retries_transient_errors_with_backoff_then_succeeds(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)
        page = [_provider_item("r1", datetime.now() - timedelta(days=1))]

        with (
            patch(
                "groww_pulse.collection.google_play_collector.fetch_play_reviews",
                side_effect=[ConnectionError("boom"), (page, None)],
            ) as mocked,
            patch("groww_pulse.collection.google_play_collector.time.sleep") as mocked_sleep,
        ):
            collector = GooglePlayReviewCollector(max_retries=3, initial_backoff_seconds=0.01)
            result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert [r.review_id for r in result] == ["r1"]
        assert mocked.call_count == 2
        mocked_sleep.assert_called_once_with(0.01)
        assert any("attempt_1" in e for e in collector.last_metrics.provider_errors)

    def test_fails_without_publishing_after_retry_budget_exhausted(self) -> None:
        cutoff = date.today() - timedelta(weeks=4)

        with (
            patch(
                "groww_pulse.collection.google_play_collector.fetch_play_reviews",
                side_effect=ConnectionError("boom"),
            ),
            patch("groww_pulse.collection.google_play_collector.time.sleep"),
        ):
            collector = GooglePlayReviewCollector(max_retries=2, initial_backoff_seconds=0.01)
            result = collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert result == []
        assert any("page_abandoned" in e for e in collector.last_metrics.provider_errors)

    def test_respects_max_pages_safety_cap(self) -> None:
        cutoff = date.today() - timedelta(weeks=52)
        page = [_provider_item("r_static", datetime.now() - timedelta(days=1))]

        with patch(
            "groww_pulse.collection.google_play_collector.fetch_play_reviews",
            return_value=(page, "always_more"),
        ) as mocked:
            collector = GooglePlayReviewCollector(max_pages=3)
            collector.collect_reviews(app_id="com.nextbillion.groww", cutoff_date=cutoff)

        assert mocked.call_count == 3
        assert collector.last_metrics.pages_read == 3

    def test_parse_locale_splits_lang_and_country(self) -> None:
        assert GooglePlayReviewCollector._parse_locale("en_IN") == ("en", "in")
        assert GooglePlayReviewCollector._parse_locale("en") == ("en", "us")

    def test_raises_no_unhandled_exception_type(self) -> None:
        assert issubclass(CollectionError, Exception)


@pytest.mark.parametrize("locale", ["en_IN", "hi_IN"])
def test_google_play_collector_passes_locale_through(locale: str) -> None:
    cutoff = date.today() - timedelta(weeks=4)
    page = [_provider_item("r1", datetime.now() - timedelta(days=1))]

    with patch(
        "groww_pulse.collection.google_play_collector.fetch_play_reviews",
        return_value=(page, None),
    ):
        collector = GooglePlayReviewCollector()
        result = collector.collect_reviews(
            app_id="com.nextbillion.groww", cutoff_date=cutoff, locale=locale
        )

    assert result[0].locale == locale
