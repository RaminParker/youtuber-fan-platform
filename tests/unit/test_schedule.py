"""The scheduling arithmetic — the part of the pipeline with no excuses."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import ScheduleSettings
from app.db.models import MailingStatus
from app.jobs.schedule import (
    MAX_ATTEMPTS,
    PREPARE_SENTIMENT,
    RETRY_CAP,
    SEND,
    SEND_PREVIEW,
    compute_send_at,
    has_attempts_left,
    next_mailing_step,
    postponed_send_at,
    preview_deadline,
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


SCHEDULE = ScheduleSettings(
    default_delay_hours=168,
    min_delay_hours=48,
    max_delay_hours=720,
    sentiment_lead_hours=2,
    stop_window_minutes=60,
    postpone_hours=24,
)
T = datetime(2026, 9, 23, 16, 0, tzinfo=UTC)


def mailing(status, send_at=T, preview_sent_at=None):
    return SimpleNamespace(status=status, send_at=send_at, preview_sent_at=preview_sent_at)


class TestNextMailingStep:
    def test_nothing_is_due_before_the_sentiment_lead(self):
        early = T - timedelta(hours=2, minutes=1)
        assert next_mailing_step(mailing(MailingStatus.SCHEDULED), early, SCHEDULE) is None

    def test_sentiment_is_fetched_two_hours_before_the_send(self):
        at = T - timedelta(hours=2)
        assert (
            next_mailing_step(mailing(MailingStatus.SCHEDULED), at, SCHEDULE) == PREPARE_SENTIMENT
        )

    def test_the_preview_waits_for_its_hour(self):
        at = T - timedelta(minutes=61)
        assert next_mailing_step(mailing(MailingStatus.SENTIMENT_READY), at, SCHEDULE) is None

    def test_the_preview_goes_out_one_hour_before_the_send(self):
        at = T - timedelta(minutes=60)
        step = next_mailing_step(mailing(MailingStatus.SENTIMENT_READY), at, SCHEDULE)
        assert step == SEND_PREVIEW

    def test_the_send_waits_for_its_time(self):
        row = mailing(MailingStatus.PREVIEW_SENT, preview_sent_at=T - timedelta(hours=1))
        assert next_mailing_step(row, T - timedelta(seconds=1), SCHEDULE) is None
        assert next_mailing_step(row, T, SCHEDULE) == SEND

    def test_a_worker_down_across_t_still_grants_the_full_stop_window(self):
        # The preview went out late, at T+5h; send_at was not pushed (an old row).
        late = T + timedelta(hours=5)
        row = mailing(MailingStatus.PREVIEW_SENT, preview_sent_at=late)

        assert next_mailing_step(row, late + timedelta(minutes=59), SCHEDULE) is None
        assert next_mailing_step(row, late + timedelta(minutes=60), SCHEDULE) == SEND

    def test_a_worker_down_across_t_runs_every_earlier_step_late(self):
        late = T + timedelta(hours=5)
        assert next_mailing_step(mailing(MailingStatus.SCHEDULED), late, SCHEDULE) == (
            PREPARE_SENTIMENT
        )
        assert next_mailing_step(mailing(MailingStatus.SENTIMENT_READY), late, SCHEDULE) == (
            SEND_PREVIEW
        )

    def test_a_started_send_resumes_whatever_the_clock(self):
        row = mailing(MailingStatus.SENDING, preview_sent_at=T - timedelta(hours=1))
        assert next_mailing_step(row, T - timedelta(days=1), SCHEDULE) == SEND

    @pytest.mark.parametrize(
        "status",
        [MailingStatus.SENT, MailingStatus.STOPPED, MailingStatus.CANCELLED, MailingStatus.FAILED],
    )
    def test_a_finished_mailing_has_no_next_step(self, status):
        assert next_mailing_step(mailing(status), T + timedelta(days=30), SCHEDULE) is None

    def test_the_preview_deadline_is_one_stop_window_before_the_send(self):
        assert preview_deadline(T, SCHEDULE) == T - timedelta(minutes=60)


class TestPostpone:
    PUBLISHED = T - timedelta(days=7)

    def test_a_postpone_adds_a_day(self):
        assert postponed_send_at(T, self.PUBLISHED, SCHEDULE) == T + timedelta(hours=24)

    def test_near_the_cap_it_stops_at_the_cap(self):
        cap = self.PUBLISHED + timedelta(hours=720)
        send_at = cap - timedelta(hours=3)

        assert postponed_send_at(send_at, self.PUBLISHED, SCHEDULE) == cap

    def test_at_the_cap_there_is_nothing_left_to_postpone(self):
        cap = self.PUBLISHED + timedelta(hours=720)
        assert postponed_send_at(cap, self.PUBLISHED, SCHEDULE) is None

    def test_a_premiere_announced_long_ago_is_capped_at_once(self):
        # published_at weeks in the past: the minimum delay already pushed the
        # send beyond published_at + max, so there is no room to postpone.
        published = NOW - timedelta(days=40)
        send_at = compute_send_at(published, DEFAULT_DELAY, NOW, MIN_DELAY)

        assert send_at == NOW + timedelta(hours=MIN_DELAY)
        assert postponed_send_at(send_at, published, SCHEDULE) is None
