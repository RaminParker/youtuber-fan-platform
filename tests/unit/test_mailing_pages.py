"""What the creator's stop and postpone pages say — without a database.

The wording is the product here: the pages are what a creator sees in the one
minute they care about a mailing. Two things must hold for every state, and
both are cheap to check without a request: the page says what actually
happened, and it never says "Gestoppt" unless it was this click that stopped it.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.db.models import MAILING_STOPPABLE, MailingStatus
from app.errors import NeedsOperator
from app.web.routes.mailings import TRUTH, _truth
from app.worker import WAIT_FOR_THE_OPERATOR, park_for_the_operator

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
FINISHED = [status for status in MailingStatus if status not in MAILING_STOPPABLE]


def found(status: str):
    """What ``find_by_token`` hands the page: a mailing, its video, its creator."""
    return (
        SimpleNamespace(status=status, send_at=NOW),
        SimpleNamespace(title="Ein Video", published_at=NOW - timedelta(days=3)),
        SimpleNamespace(accent_color="#333333", name="Kanal", slug="kanal"),
    )


def page_text(response) -> str:
    return response.body.decode()


class TestTheTruthTable:
    @pytest.mark.parametrize("status", FINISHED)
    def test_every_state_a_link_cannot_change_has_wording(self, status):
        # Without this, a state added later reaches the page as a KeyError — a
        # 500 in the one place a creator is trying to stop a mail.
        assert status in TRUTH

    @pytest.mark.parametrize("status", FINISHED)
    def test_and_none_of_it_claims_the_mail_was_just_stopped(self, status):
        heading, message = TRUTH[status]

        assert "Gestoppt" not in heading
        assert heading and message

    def test_a_mail_on_its_way_says_so(self):
        response = _truth(found(MailingStatus.SENDING))

        assert response.status_code == 409
        assert "schon unterwegs" in page_text(response)
        assert 'role="alert"' in page_text(response)

    def test_an_already_stopped_mail_says_it_was_already_stopped(self):
        text = page_text(_truth(found(MailingStatus.STOPPED)))

        assert "bereits gestoppt" in text
        assert "<h1>Gestoppt</h1>" not in text

    def test_an_unknown_token_points_at_the_newer_preview(self):
        response = _truth(None)

        assert response.status_code == 410
        assert "neuere Vorschau" in page_text(response)

    def test_a_lost_race_asks_to_open_the_link_again(self):
        # The mailing is still stoppable, so the write lost to another writer.
        response = _truth(found(MailingStatus.PREVIEW_SENT), raced=True)

        assert "noch einmal" in page_text(response)


class TestParkingAKeyProblem:
    """A rejected key costs neither an attempt nor a video (see app/errors.py)."""

    def error(self) -> NeedsOperator:
        return NeedsOperator("YouTube Data API", "API key rejected", "check YOUTUBE_API_KEY")

    def test_the_row_waits_an_hour_and_keeps_its_attempts(self):
        row = SimpleNamespace(attempts=3, next_attempt_at=None, last_error=None)

        park_for_the_operator(row, self.error(), NOW)

        assert row.attempts == 3
        assert row.next_attempt_at == NOW + WAIT_FOR_THE_OPERATOR

    def test_the_row_carries_the_whole_message_for_the_operator(self):
        row = SimpleNamespace(attempts=0, next_attempt_at=None, last_error=None)

        park_for_the_operator(row, self.error(), NOW)

        assert "YOUTUBE_API_KEY" in row.last_error
        assert "API key rejected" in row.last_error

    def test_an_hour_is_short_enough_to_pick_up_a_fix_the_same_morning(self):
        assert timedelta(hours=1) >= WAIT_FOR_THE_OPERATOR
