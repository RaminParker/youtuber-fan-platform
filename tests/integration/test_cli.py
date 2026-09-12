"""Operator commands. The CLI ingests and reports; it never runs a step."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import cli
from app.db.engine import session_scope
from app.db.models import Appearance, AppearanceStatus, Creator, Source
from app.services import set_services
from app.sources.base import SourceProfile
from tests import fakes
from tests.fakes import FakeYouTubeConnector, content_item

pytestmark = pytest.mark.integration

CHANNEL = "UCpilot0000000000000000"
AVATAR = "https://yt3.example/pilot.jpg"


@pytest.fixture
def connector(committed_database, fake_services):
    connector = FakeYouTubeConnector(
        items=[content_item("aaaaaaaaaaa", title="Warum Verwaltung so langsam ist")],
        profile=SourceProfile(external_id=CHANNEL, title="Pilotkanal", avatar_url=AVATAR),
    )
    set_services(fakes.services(youtube=connector))
    return connector


def onboard():
    cli.main(
        [
            "onboard",
            "--slug",
            "pilot",
            "--name",
            "Pilotkanal",
            "--email",
            "Pilot@Example.org",
            "--channel-id",
            CHANNEL,
        ]
    )


class TestOnboard:
    def test_it_creates_the_creator_and_the_source(self, connector, capsys):
        onboard()

        with session_scope() as session:
            creator = session.scalar(select(Creator).where(Creator.slug == "pilot"))
            source = session.scalar(select(Source))
            assert creator.name == "Pilotkanal"
            assert source.external_id == CHANNEL
            assert source.title == "Pilotkanal"

    def test_the_channel_avatar_becomes_the_default_logo(self, connector):
        # A real picture beats an empty header on day one, and the creator can
        # replace it on the settings page.
        onboard()

        with session_scope() as session:
            assert session.scalar(select(Creator)).logo_url == AVATAR

    def test_the_contact_address_is_stored_lower_cased(self, connector):
        onboard()

        with session_scope() as session:
            assert session.scalar(select(Creator)).contact_email == "pilot@example.org"

    def test_it_prints_the_sign_up_link_the_creator_has_to_publish(self, connector, capsys):
        onboard()

        assert "/k/pilot" in capsys.readouterr().out

    def test_an_unknown_channel_stops_before_writing_anything(
        self, committed_database, fake_services
    ):
        set_services(fakes.services(youtube=FakeYouTubeConnector(profile=None)))

        with pytest.raises(SystemExit):
            onboard()

        with session_scope() as session:
            assert session.scalar(select(Creator)) is None


class TestProcess:
    def test_it_records_one_item_back_catalogue_included(self, connector, capsys):
        onboard()

        cli.main(["process", "pilot", "aaaaaaaaaaa"])

        with session_scope() as session:
            appearance = session.scalar(select(Appearance))
            assert appearance.external_id == "aaaaaaaaaaa"
            assert appearance.status == AppearanceStatus.DETECTED

    def test_it_never_runs_the_step_itself(self, connector):
        # Two runners would repeat expensive steps on the same row, so the CLI
        # stops at `detected` and leaves the work to the worker.
        onboard()

        cli.main(["process", "pilot", "aaaaaaaaaaa"])

        with session_scope() as session:
            assert session.scalar(select(Appearance)).status == AppearanceStatus.DETECTED

    def test_ingesting_the_same_item_twice_is_harmless(self, connector, capsys):
        onboard()

        cli.main(["process", "pilot", "aaaaaaaaaaa"])
        cli.main(["process", "pilot", "aaaaaaaaaaa"])

        assert "already recorded" in capsys.readouterr().out
        with session_scope() as session:
            assert len(session.scalars(select(Appearance)).all()) == 1

    def test_an_unknown_slug_is_refused(self, connector):
        with pytest.raises(SystemExit):
            cli.main(["process", "nobody", "aaaaaaaaaaa"])

    def test_an_unknown_video_is_refused(self, connector):
        onboard()

        with pytest.raises(SystemExit):
            cli.main(["process", "pilot", "doesnotexis"])


class TestTimestamps:
    def test_the_source_records_when_it_was_onboarded(self, connector):
        # Everything published before that moment is back catalogue.
        before = datetime.now(UTC)

        onboard()

        with session_scope() as session:
            assert session.scalar(select(Source)).created_at >= before


class TestEvalPrompts:
    """Prompts are product; this command is how a change to one is judged."""

    def test_it_renders_every_sample_transcript(self, connector, tmp_path, fake_services):
        from tests.fakes import FakeLLMGateway

        gateway = FakeLLMGateway()
        set_services(fakes.services(llm=gateway))

        cli.main(["eval-prompts", "--out", str(tmp_path)])

        written = sorted(p.name for p in tmp_path.glob("*.md"))
        assert written == ["de_kurz.v1.md", "de_vortrag.v1.md", "en_interview.v1.md"]
        assert len(gateway.calls) == 3

    def test_the_output_is_meant_for_a_human_to_read(self, connector, tmp_path, fake_services):
        from tests.fakes import FakeLLMGateway

        set_services(fakes.services(llm=FakeLLMGateway()))

        cli.main(["eval-prompts", "--out", str(tmp_path)])

        rendered = (tmp_path / "de_vortrag.v1.md").read_text(encoding="utf-8")
        assert rendered.startswith("# ")
        assert "## Kernaussage" in rendered
        assert "## Zitat" in rendered

    def test_the_real_transcript_reaches_the_model_with_its_timestamps(
        self, connector, tmp_path, fake_services
    ):
        from tests.fakes import FakeLLMGateway

        gateway = FakeLLMGateway()
        set_services(fakes.services(llm=gateway))

        cli.main(["eval-prompts", "--out", str(tmp_path)])

        spoken = gateway.calls[1]["user"]  # de_vortrag
        assert "[07:20] Es liegt nicht an den Menschen" in spoken


class TestFailingReadably:
    """The first command an operator runs is `onboard`, often before the keys.

    A stack trace tells them nothing they can act on, so the expected ways the
    outside world says no become a message and an exit code. A bug still gets
    its traceback.
    """

    def test_a_refused_api_call_names_the_key_to_check(self, committed_database, fake_services):
        from app.sources.youtube.data_api import YouTubeError

        set_services(
            fakes.services(
                youtube=FakeYouTubeConnector(
                    fail_with=YouTubeError("channels.list: HTTP 403 forbidden")
                )
            )
        )

        with pytest.raises(SystemExit) as exited:
            onboard()

        message = str(exited.value)
        assert "403" in message
        assert "YOUTUBE_API_KEY" in message
        assert "Traceback" not in message

    def test_a_temporary_failure_is_a_message_too(self, committed_database, fake_services):
        from app.errors import TemporaryError

        set_services(
            fakes.services(
                youtube=FakeYouTubeConnector(fail_with=TemporaryError("connection refused"))
            )
        )

        with pytest.raises(SystemExit) as exited:
            onboard()

        assert "connection refused" in str(exited.value)

    def test_a_real_bug_still_gets_its_traceback(self, committed_database, fake_services):
        # Swallowing this would hide a defect behind a friendly sentence.
        set_services(
            fakes.services(
                youtube=FakeYouTubeConnector(
                    fail_with=ValueError("this is a bug, not a missing key")
                )
            )
        )

        with pytest.raises(ValueError):
            onboard()
