"""SubRip parsing. Caption files in the wild are not well-formed documents."""

from app.transcripts.srt import parse_srt, to_seconds

WELL_FORMED = """1
00:00:01,000 --> 00:00:04,500
Guten Abend und willkommen.

2
00:00:04,500 --> 00:00:09,250
Heute geht es um die Frage,
warum Verwaltung so langsam ist.
"""


class TestTimestamps:
    def test_a_plain_timestamp(self):
        assert to_seconds("00:00:04,500") == 4.5

    def test_hours_and_minutes_add_up(self):
        assert to_seconds("01:02:03,000") == 3723.0

    def test_a_dot_works_like_a_comma(self):
        # Both spellings occur; refusing one would drop a whole transcript.
        assert to_seconds("00:00:04.500") == 4.5


class TestParsing:
    def test_every_cue_becomes_a_segment(self):
        segments = parse_srt(WELL_FORMED)

        assert len(segments) == 2
        assert segments[0].text == "Guten Abend und willkommen."

    def test_the_duration_is_the_difference(self):
        assert parse_srt(WELL_FORMED)[0].duration == 3.5

    def test_a_multi_line_cue_becomes_one_segment(self):
        assert parse_srt(WELL_FORMED)[1].text == (
            "Heute geht es um die Frage, warum Verwaltung so langsam ist."
        )

    def test_windows_line_endings_parse_the_same(self):
        assert parse_srt(WELL_FORMED.replace("\n", "\r\n")) == parse_srt(WELL_FORMED)


class TestRobustness:
    def test_formatting_tags_are_stripped(self):
        tagged = "1\n00:00:01,000 --> 00:00:02,000\n<i>kursiv</i> und <b>fett</b>\n"

        assert parse_srt(tagged)[0].text == "kursiv und fett"

    def test_a_cue_without_timing_is_skipped(self):
        broken = WELL_FORMED + "\n3\nkeine Zeitangabe hier\n"

        assert len(parse_srt(broken)) == 2

    def test_an_empty_cue_is_skipped(self):
        empty = "1\n00:00:01,000 --> 00:00:02,000\n\n\n2\n00:00:02,000 --> 00:00:03,000\nText\n"

        assert [s.text for s in parse_srt(empty)] == ["Text"]

    def test_an_empty_document_yields_nothing(self):
        assert parse_srt("") == []

    def test_a_missing_cue_number_is_fine(self):
        # Some generators omit it entirely.
        assert len(parse_srt("00:00:01,000 --> 00:00:02,000\nText\n")) == 1
