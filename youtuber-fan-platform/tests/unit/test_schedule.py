"""The scheduling arithmetic — the part of the pipeline with no excuses."""

from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.schedule import (
    MAX_ATTEMPTS,
    RETRY_CAP,
    compute_send_at,
    has_attempts_left,
    retry_at,
)

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
MIN_DELAY = 48
DEFAULT_DELAY = 168


class TestComputeSendAt:
    def test_a_fresh_upload_is_mailed_after_the_creators_delay(self):
        published = NOW - timedelta(hours=1)

        send_at = compute_send_at(published, DEFAULT_DELAY, NOW, MIN_DELAY)

        assert send_at == published + timedelta(hours=DEFAULT_DELAY)

    def test_the_minimum_wins_over_a_shorter_creator_delay(self):
        published = NOW

        send_at = compute_send_at(published, 2, NOW, MIN_DELAY)

        assert send_at == NOW + timedelta(hours=MIN_DELAY)

    def test_a_back_catalogue_video_is_never_mailed_immediately(self):
        # Published two years ago: published_at + delay is long past.
        published = NOW - timedelta(days=730)

        send_at = compute_send_at(published, DEFAULT_DELAY, NOW, MIN_DELAY)

        assert send_at == NOW + timedelta(hours=MIN_DELAY)

    def test_shortening_the_delay_below_the_elapsed_time_still_honours_the_minimum(self):
        # The creator drops 7 days to 2 on a video published 5 days ago.
        published = NOW - timedelta(days=5)

        send_at = compute_send_at(published, 48, NOW, MIN_DELAY)

        assert send_at == NOW + timedelta(hours=MIN_DELAY)
        assert send_at >= NOW + timedelta(hours=MIN_DELAY)

    def test_a_premiere_counts_from_go_live_not_from_its_announcement(self):
        # published_at is already actualStartTime by the time we get here.
        went_live = NOW - timedelta(hours=3)

        send_at = compute_send_at(went_live, DEFAULT_DELAY, NOW, MIN_DELAY)

        assert send_at == went_live + timedelta(hours=DEFAULT_DELAY)

    @pytest.mark.parametrize("delay", [48, 72, 168, 720])
    def test_the_result_is_never_below_the_floor(self, delay):
        for age_days in (0, 1, 7, 400):
            send_at = compute_send_at(NOW - timedelta(days=age_days), delay, NOW, MIN_DELAY)

            assert send_at >= NOW + timedelta(hours=MIN_DELAY)


class TestRetryAt:
    def test_the_first_retry_comes_after_five_minutes(self):
        assert retry_at(1, NOW) == NOW + timedelta(minutes=5)

    @pytest.mark.parametrize(
        ("attempts", "minutes"),
        [(1, 5), (2, 10), (3, 20), (4, 40), (5, 80), (6, 160), (7, 320)],
    )
    def test_the_wait_doubles_until_it_hits_the_cap(self, attempts, minutes):
        assert retry_at(attempts, NOW) == NOW + timedelta(minutes=minutes)

    @pytest.mark.parametrize("attempts", [8, 9, 10, 25, 1000])
    def test_the_wait_never_exceeds_six_hours(self, attempts):
        assert retry_at(attempts, NOW) == NOW + RETRY_CAP

    def test_the_whole_ladder_fits_inside_the_minimum_delay(self):
        # If it did not, a day of trouble would cost a mail rather than delay it.
        total = sum((retry_at(n, NOW) - NOW for n in range(1, MAX_ATTEMPTS)), start=timedelta())

        assert total < timedelta(hours=MIN_DELAY)
        assert timedelta(hours=22) < total < timedelta(hours=23)


class TestAttemptsLeft:
    def test_a_fresh_row_may_be_tried(self):
        assert has_attempts_left(0) is True

    def test_the_last_allowed_attempt_is_the_tenth(self):
        assert has_attempts_left(MAX_ATTEMPTS - 1) is True
        assert has_attempts_left(MAX_ATTEMPTS) is False
