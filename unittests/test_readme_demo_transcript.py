"""Tests for the readme-demo transcript parser (renderer input)."""

import textwrap

import pytest

from sapguimcp.demo.render_readme_demo import Beat, Mark, ParseError, parse_transcript


class TestParseTranscript:
    def test_parses_minimal_beat(self) -> None:
        text = textwrap.dedent(
            """\
            [beat 2] role=assistant
            Logging into the dev system…
            tool=sap_login
            """
        )
        beats = parse_transcript(text)
        assert beats == [
            Beat(number=2, role="assistant", message="Logging into the dev system…", tool="sap_login", frame=None),
        ]

    def test_parses_user_beat_multiline_message(self) -> None:
        text = textwrap.dedent(
            """\
            [beat 1] role=user
            Log into the dev system, create business partner
            Max Mustermann, and verify in SE16.
            """
        )
        beats = parse_transcript(text)
        assert beats[0].role == "user"
        expected_message = "Log into the dev system, create business partner\nMax Mustermann, and verify in SE16."
        assert beats[0].message == expected_message
        assert beats[0].tool is None
        assert beats[0].frame is None

    def test_parses_beat_with_frame(self) -> None:
        text = textwrap.dedent(
            """\
            [beat 8] role=assistant frame=frames/08_se16_result.png
            Now verifying in SE16 that it exists…
            tool=sap_se16_query
            """
        )
        beats = parse_transcript(text)
        assert beats[0].frame == "frames/08_se16_result.png"

    def test_frame_may_repeat_an_earlier_file(self) -> None:
        text = textwrap.dedent(
            """\
            [beat 6] role=assistant frame=frames/07_bp_saved.png
            Saved.
            tool=sap_press_key

            [beat 7] role=assistant frame=frames/07_bp_saved.png
            Capturing a screenshot for the documentation…
            tool=sap_screenshot
            """
        )
        beats = parse_transcript(text)
        assert [b.frame for b in beats] == ["frames/07_bp_saved.png", "frames/07_bp_saved.png"]

    def test_parses_full_storyboard(self) -> None:
        text = textwrap.dedent(
            """\
            [beat 0] role=title
            SAP GUI MCP — chat with Claude, watch SAP do the work

            [beat 1] role=user
            Log into the dev system, create business partner Max Mustermann,
            save it, take a screenshot, and verify in SE16.

            [beat 2] role=assistant
            Logging into the dev system…
            tool=sap_login
            """
        )
        beats = parse_transcript(text)
        assert [b.number for b in beats] == [0, 1, 2]
        assert beats[0].role == "title"

    def test_rejects_beat_without_number(self) -> None:
        text = "[beat x] role=assistant\nHello\n"
        with pytest.raises(ParseError, match="does not start"):
            parse_transcript(text)

    def test_rejects_unknown_role(self) -> None:
        text = "[beat 1] role=wizard\nHello\n"
        with pytest.raises(ParseError, match="role"):
            parse_transcript(text)

    def test_rejects_empty_message(self) -> None:
        text = "[beat 1] role=user\n\n"
        with pytest.raises(ParseError, match="message"):
            parse_transcript(text)

    def test_rejects_tool_key_on_user_beat(self) -> None:
        text = "[beat 1] role=user\nHello\ntool=sap_login\n"
        with pytest.raises(ParseError, match="tool"):
            parse_transcript(text)

    def test_rejects_duplicate_beat_number(self) -> None:
        text = "[beat 1] role=user\nHello\n\n[beat 1] role=assistant\nHi\n"
        with pytest.raises(ParseError, match="Duplicate"):
            parse_transcript(text)

    def test_rejects_unknown_header_key(self) -> None:
        text = "[beat 1] role=assistant fram=frames/08.png\nHello\n"
        with pytest.raises(ParseError, match="fram"):
            parse_transcript(text)

    def test_rejects_tool_in_header(self) -> None:
        text = "[beat 1] role=assistant tool=sap_login\nHello\n"
        with pytest.raises(ParseError, match="own line"):
            parse_transcript(text)

    def test_tool_line_before_message(self) -> None:
        text = "[beat 3] role=assistant\ntool=sap_login\nLogging into the dev system…\n"
        beats = parse_transcript(text)
        assert beats == [
            Beat(number=3, role="assistant", message="Logging into the dev system…", tool="sap_login", frame=None),
        ]

    def test_parses_crlf_transcript(self) -> None:
        lf = textwrap.dedent(
            """\
            [beat 2] role=assistant
            Logging into the dev system…
            tool=sap_login
            """
        )
        beats = parse_transcript(lf.replace("\n", "\r\n"))
        assert beats == parse_transcript(lf)


class TestParseOverlays:
    def test_parses_marks_and_status(self) -> None:
        text = textwrap.dedent(
            """\
            [beat 5] role=assistant frame=frames/05.png
            Filling in name…
            tool=sap_fill_form
            mark=242,404,409,25 Vorname = Max
            mark=8,853,1029,40
            status=8,853,1029,40 Saved
            """
        )
        beat = parse_transcript(text)[0]
        assert beat.marks == (Mark(242, 404, 409, 25, "Vorname = Max"), Mark(8, 853, 1029, 40, ""))
        assert beat.status == Mark(8, 853, 1029, 40, "Saved")
        assert beat.message == "Filling in name…"

    def test_user_beat_cannot_carry_marks(self) -> None:
        with pytest.raises(ParseError, match="only assistant beats"):
            parse_transcript("[beat 1] role=user\nHello\nmark=1,2,3,4 x\n")

    def test_second_status_line_rejected(self) -> None:
        with pytest.raises(ParseError, match="more than one status"):
            parse_transcript("[beat 2] role=assistant\nHi\nstatus=1,2,3,4 a\nstatus=1,2,3,4 b\n")

    @pytest.mark.parametrize("line", ["mark=1,2,3 caption", "status=oops", "mark=1,2,3,x y"])
    def test_malformed_overlay_line_is_rejected(self, line: str) -> None:
        with pytest.raises(ParseError, match="malformed overlay line"):
            parse_transcript(f"[beat 2] role=assistant\nHi\n{line}\n")
