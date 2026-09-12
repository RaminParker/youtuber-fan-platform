"""Composing the mail a fan receives — and the preview the creator approves."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.analysis.schemas import Sentiment, Summary
from app.config import get_settings
from app.db.models import Creator
from app.delivery.render import render_summary_mail, snapshot_of
from tests.fakes import _default_for

SEND_AT = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)


@pytest.fixture
def creator():
    return Creator(
        slug="pilot",
        name="Pilotkanal",
        contact_email="pilot@example.org",
        accent_color="#c4452d",
        greeting_text="Servus!",
        farewell_text="Bis nächste Woche.",
    )


@pytest.fixture
def appearance():
    return SimpleNamespace(
        title="Warum Verwaltung so langsam ist",
        url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
    )


@pytest.fixture
def subscription():
    return SimpleNamespace(
        unsubscribe_token="unsub-token",
        confirmed_at=datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
        subscriber=SimpleNamespace(email="fan@example.org"),
    )


def build(creator, appearance, default_subscription, **overrides):
    """Render a mail, with everything a test does not care about filled in."""
    defaults = dict(
        creator=creator,
        appearance=appearance,
        summary=_default_for(Summary),
        sentiment=_default_for(Sentiment),
        subscription=default_subscription,
        settings=get_settings(),
        variant="compact",
        view_url="https://klartext.tld/s/view-token",
    )
    return render_summary_mail(**(defaults | overrides))


class TestTheFixedFrame:
    def test_the_sender_names_the_creator_and_the_platform(self, creator, appearance, subscription):
        # The fan sees whose mail it is and who built it, before opening it.
        mail = build(creator, appearance, subscription)

        assert mail.from_ == "Pilotkanal via Klartext <post@mail.klartext.tld>"

    def test_the_subject_is_the_creator_and_the_title(self, creator, appearance, subscription):
        assert build(creator, appearance, subscription).subject == (
            "Pilotkanal: Warum Verwaltung so langsam ist"
        )

    def test_replies_reach_the_creator_when_they_set_an_address(
        self, creator, appearance, subscription
    ):
        creator.reply_to_email = "post@pilotkanal.de"

        assert build(creator, appearance, subscription).reply_to == "post@pilotkanal.de"

    def test_and_otherwise_reach_us(self, creator, appearance, subscription):
        # Never a no-reply: a fan writing back is the best thing that can happen.
        assert build(creator, appearance, subscription).reply_to == "hallo@klartext.tld"

    def test_the_creators_two_sentences_are_where_they_belong(
        self, creator, appearance, subscription
    ):
        mail = build(creator, appearance, subscription)

        assert mail.text.index("Servus!") < mail.text.index("Warum Verwaltung")
        assert mail.text.index("Bis nächste Woche.") > mail.text.index("Warum Verwaltung")

    def test_the_notice_is_in_both_parts(self, creator, appearance, subscription):
        mail = build(creator, appearance, subscription)

        assert "kein Ersatz für das Original" in mail.html
        assert "kein Ersatz für das Original" in mail.text


class TestUnsubscribing:
    def test_the_one_click_headers_are_set(self, creator, appearance, subscription):
        mail = build(creator, appearance, subscription)

        assert mail.headers["List-Unsubscribe"] == ("<https://klartext.tld/abmelden/unsub-token>")
        assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_the_link_is_in_the_body_too(self, creator, appearance, subscription):
        # Not every client shows the header button.
        assert "/abmelden/unsub-token" in build(creator, appearance, subscription).text

    def test_the_footer_says_why_this_mail_arrived(self, creator, appearance, subscription):
        assert "03.08.2026" in build(creator, appearance, subscription).text


class TestVariants:
    def test_compact_lists_the_key_points(self, creator, appearance, subscription):
        html = build(creator, appearance, subscription, variant="compact").html

        assert "Zuständigkeiten sind zersplittert." in html
        assert "Das Problem" not in html

    def test_detailed_lists_the_sections(self, creator, appearance, subscription):
        html = build(creator, appearance, subscription, variant="detailed").html

        assert "Das Problem" in html

    def test_teaser_sends_the_reader_to_the_page(self, creator, appearance, subscription):
        html = build(creator, appearance, subscription, variant="teaser").html

        assert "Weiterlesen" in html
        assert "https://klartext.tld/s/view-token" in html

    def test_all_of_them_come_from_one_analysis(self, creator, appearance, subscription):
        # Which is what lets a creator change their mind without re-summarising.
        rendered = {
            v: build(creator, appearance, subscription, variant=v).html
            for v in ("compact", "detailed", "teaser")
        }

        assert len(set(rendered.values())) == 3

    def test_the_compact_mail_stays_short(self, creator, appearance, subscription):
        mail = build(creator, appearance, subscription, variant="compact")

        assert len(mail.text.split()) < 300


class TestSentiment:
    def test_the_box_appears_when_there_is_one(self, creator, appearance, subscription):
        assert "Wie die Community reagiert hat" in build(creator, appearance, subscription).html

    def test_and_the_mail_is_fine_without_it(self, creator, appearance, subscription):
        # Comments off, or nothing surviving the filter: the feature degrades,
        # the mail does not break.
        mail = build(creator, appearance, subscription, sentiment=None)

        assert "Wie die Community reagiert hat" not in mail.html
        assert "Warum Verwaltung so langsam ist" in mail.html


class TestJumpLinks:
    def test_they_point_into_the_video(self, creator, appearance, subscription):
        assert "watch?v=aaaaaaaaaaa&t=61s" in build(creator, appearance, subscription).text

    def test_a_point_without_a_timestamp_simply_has_no_link(
        self, creator, appearance, subscription
    ):
        summary = _default_for(Summary)
        summary.key_points[0].timestamp_seconds = None

        text = build(creator, appearance, subscription, summary=summary).text

        assert "Zuständigkeiten sind zersplittert.\n" in text


class TestThePreview:
    def test_it_goes_to_the_creator_not_to_a_fan(self, creator, appearance, subscription):
        mail = build(
            creator,
            appearance,
            subscription,
            subscription=None,
            stop_token="stop-token",
            send_at=SEND_AT,
        )

        assert mail.to == "pilot@example.org"

    def test_it_carries_the_stop_and_postpone_links(self, creator, appearance, subscription):
        mail = build(
            creator,
            appearance,
            subscription,
            subscription=None,
            stop_token="stop-token",
            send_at=SEND_AT,
        )

        assert "/m/stop-token/stoppen" in mail.text
        assert "/m/stop-token/verschieben" in mail.text

    def test_it_says_when_the_mail_would_go_out(self, creator, appearance, subscription):
        mail = build(
            creator,
            appearance,
            subscription,
            subscription=None,
            stop_token="stop-token",
            send_at=SEND_AT,
        )

        assert "17.09.2026" in mail.text

    def test_it_has_no_unsubscribe_headers(self, creator, appearance, subscription):
        # There is nothing for the creator to unsubscribe from.
        mail = build(
            creator,
            appearance,
            subscription,
            subscription=None,
            stop_token="stop-token",
            send_at=SEND_AT,
        )

        assert mail.headers == {}

    def test_it_is_otherwise_the_same_mail(self, creator, appearance, subscription):
        # A preview that differed from what goes out would be worse than none.
        fan_mail = build(creator, appearance, subscription)
        preview = build(
            creator,
            appearance,
            subscription,
            subscription=None,
            stop_token="stop-token",
            send_at=SEND_AT,
        )

        assert "Es liegt nicht an den Menschen" in preview.html
        assert preview.subject == fan_mail.subject


class TestTheFrozenRendering:
    """What the creator approved is what the fans get, and what a retry repeats."""

    def test_a_snapshot_captures_what_a_rendered_mail_depends_on(self, creator):
        frozen = snapshot_of(creator, "detailed")

        assert frozen["greeting_text"] == "Servus!"
        assert frozen["email_variant"] == "detailed"

    def test_later_changes_do_not_reach_a_frozen_mailing(self, creator, appearance, subscription):
        frozen = snapshot_of(creator, "compact")
        creator.greeting_text = "Ganz was anderes"
        creator.name = "Umbenannt"

        mail = build(creator, appearance, subscription, snapshot=frozen)

        assert "Servus!" in mail.text
        assert "Ganz was anderes" not in mail.text
        assert mail.subject.startswith("Pilotkanal:")

    def test_a_frozen_mailing_renders_byte_identically_twice(
        self, creator, appearance, subscription
    ):
        # This is what makes a stable idempotency key safe on a retry.
        frozen = snapshot_of(creator, "compact")
        first = build(creator, appearance, subscription, snapshot=frozen).html
        creator.accent_color = "#000000"

        second = build(creator, appearance, subscription, snapshot=frozen).html

        assert first == second

    def test_without_a_snapshot_the_live_creator_is_used(self, creator, appearance, subscription):
        creator.greeting_text = "Neuer Gruß"

        assert "Neuer Gruß" in build(creator, appearance, subscription).text
