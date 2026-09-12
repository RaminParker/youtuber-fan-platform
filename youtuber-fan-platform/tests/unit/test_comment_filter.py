"""The comment filter: the cheapest quality lever in the product."""

import pytest

from app.analysis.comments import as_prompt_lines, filter_comments, normalise
from app.config import CommentSettings
from app.sources.base import Comment

OWNER = "UCpilot0000000000000000"


@pytest.fixture
def settings():
    return CommentSettings(
        max_count=300, min_words=5, drop_with_links=True, drop_channel_owner=True
    )


def comment(text: str, likes: int = 0, author: str | None = "UCfan") -> Comment:
    return Comment(text=text, like_count=likes, author_channel_id=author)


def texts(result):
    return [c.text for c in result]


class TestLength:
    def test_a_substantial_comment_is_kept(self, settings):
        keeper = comment("Endlich sagt das mal jemand so deutlich, danke dafür")

        assert filter_comments([keeper], settings) == [keeper]

    @pytest.mark.parametrize("text", ["erster", "top", "sehr gut", "danke dir sehr"])
    def test_short_reactions_are_dropped(self, settings, text):
        assert filter_comments([comment(text)], settings) == []

    def test_exactly_the_minimum_is_kept(self, settings):
        assert len(filter_comments([comment("eins zwei drei vier fünf")], settings)) == 1


class TestLinks:
    def test_a_comment_with_a_link_is_dropped(self, settings):
        spam = comment("Schaut mal hier vorbei https://example.com für mehr")

        assert filter_comments([spam], settings) == []

    def test_a_bare_domain_counts_as_a_link(self, settings):
        assert (
            filter_comments([comment("Mehr dazu auf beispiel.de findet ihr dort")], settings) == []
        )

    def test_the_rule_can_be_switched_off(self, settings):
        settings = settings.model_copy(update={"drop_with_links": False})

        assert (
            len(filter_comments([comment("Quelle: https://example.com dazu gibt es")], settings))
            == 1
        )


class TestTheChannelItself:
    def test_the_creators_own_replies_are_dropped(self, settings):
        # They are part of the conversation, but not part of the community's
        # reaction to it.
        own = comment("Danke euch allen für die Diskussion hier unten", author=OWNER)

        assert filter_comments([own], settings, channel_id=OWNER) == []

    def test_without_a_channel_id_nothing_is_dropped_for_it(self, settings):
        own = comment("Danke euch allen für die Diskussion hier unten", author=OWNER)

        assert len(filter_comments([own], settings)) == 1


class TestDuplicates:
    def test_the_same_text_twice_is_kept_once(self, settings):
        text = "Bei Minute zwölf liegst du daneben leider"

        assert len(filter_comments([comment(text), comment(text)], settings)) == 1

    def test_punctuation_and_case_do_not_make_it_a_new_comment(self, settings):
        first = comment("Bei Minute zwölf liegst du daneben")
        second = comment("BEI MINUTE ZWÖLF LIEGST DU DANEBEN!!!")

        assert len(filter_comments([first, second], settings)) == 1

    def test_emoji_padding_does_not_either(self, settings):
        first = comment("Bei Minute zwölf liegst du daneben")
        second = comment("Bei Minute zwölf liegst du daneben 🔥🔥🔥")

        assert len(filter_comments([first, second], settings)) == 1

    def test_a_genuinely_different_comment_survives(self, settings):
        first = comment("Bei Minute zwölf liegst du daneben leider")
        second = comment("Bei Minute vierzehn hast du völlig recht")

        assert len(filter_comments([first, second], settings)) == 2


class TestOrderAndCap:
    def test_the_relevance_order_is_left_alone(self, settings):
        # It is YouTube's own ranking by likes and replies; we only remove.
        given = [comment(f"Ein Kommentar mit Nummer {n} darin", likes=n) for n in range(5)]

        assert texts(filter_comments(given, settings)) == texts(given)

    def test_the_cap_stops_the_list(self, settings):
        settings = settings.model_copy(update={"max_count": 3})
        given = [comment(f"Ein Kommentar mit Nummer {n} darin") for n in range(10)]

        assert len(filter_comments(given, settings)) == 3


class TestPromptLines:
    def test_only_likes_and_text_reach_the_model(self, settings):
        rendered = as_prompt_lines(
            [comment("Ein guter Punkt war das schon", likes=412, author=OWNER)]
        )

        assert rendered == "[412] Ein guter Punkt war das schon"
        assert OWNER not in rendered

    def test_an_empty_list_renders_to_nothing(self):
        assert as_prompt_lines([]) == ""


class TestNormalise:
    def test_it_ignores_accents_case_and_punctuation(self):
        assert normalise("Grüße, Welt!") == normalise("grusse welt")
