"""Tests for the readme-demo composite renderer (layout + assembler)."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from sapguimcp.demo.render_readme_demo import (
    BACKGROUND,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CHAT_WIDTH,
    MARK_COLOR,
    OUTER_MARGIN,
    TITLE_HEIGHT,
    TOOL_FONT_SIZE,
    Beat,
    RenderError,
    _font,
    _measure_bubble,
    _tool_font,
    render_composites,
)


def _write_frame(path: Path, size: tuple[int, int] = (400, 300), color: str = "#204a87") -> None:
    Image.new("RGB", size, color).save(path)


def _sample_transcript(frames_dir: Path) -> str:
    """Two-beat transcript with real frame files on disk."""
    _write_frame(frames_dir / "02_easy_access.png")
    return (
        "[beat 0] role=title\n"
        "SAP GUI MCP — chat with Claude, watch SAP do the work\n"
        "\n"
        "[beat 1] role=user\n"
        "Create business partner Max Mustermann.\n"
        "\n"
        "[beat 2] role=assistant frame=frames/02_easy_access.png\n"
        "Logging into the dev system…\n"
        "tool=sap_login\n"
    )


class TestMeasureBubble:
    def test_bubble_is_wide_enough_for_tool_chip(self) -> None:
        draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        body_font, tool_font = _font(20), _tool_font(TOOL_FONT_SIZE)
        beat = Beat(number=6, role="assistant", message="Saving…", tool="sap_press_key Ctrl+S")
        width, _, _, _ = _measure_bubble(draw, beat, body_font, tool_font, 400)
        # chip starts 12px (padding) + 14px (triangle gutter) in and needs 12px right padding
        assert width >= 12 + 14 + draw.textlength(beat.tool or "", font=tool_font) + 12 - 1


class TestOverlays:
    @staticmethod
    def _render(workdir: Path, extra: str) -> Image.Image:
        frames = workdir / "frames"
        frames.mkdir(parents=True)
        _write_frame(frames / "02_easy_access.png", (1045, 901))
        (workdir / "transcript.md").write_text(
            "[beat 1] role=assistant frame=frames/02_easy_access.png\nTyping…\ntool=sap_fill_form\n" + extra,
            encoding="utf-8",
        )
        render_composites(workdir / "transcript.md", frames, workdir / "composite")
        return Image.open(workdir / "composite" / "composite_01.png").convert("RGB")

    def test_mark_draws_ring_and_caption_over_frame(self, tmp_path: Path) -> None:
        plain = self._render(tmp_path / "plain", "")
        marked = self._render(tmp_path / "marked", "mark=242,404,409,25 Max\n")
        assert plain.tobytes() != marked.tobytes()
        sap_panel = [(x, y) for x in range(CHAT_WIDTH, CANVAS_WIDTH) for y in range(TITLE_HEIGHT, CANVAS_HEIGHT)]
        assert any(marked.getpixel(xy) == MARK_COLOR for xy in sap_panel)
        assert not any(plain.getpixel(xy) == MARK_COLOR for xy in sap_panel)

    def test_status_text_changes_the_frame(self, tmp_path: Path) -> None:
        plain = self._render(tmp_path / "plain", "")
        with_status = self._render(tmp_path / "status", "status=8,853,1029,40 Saved\n")
        assert plain.tobytes() != with_status.tobytes()


class TestRenderComposites:
    def test_renders_one_composite_per_beat(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        out = tmp_path / "composite"
        (frames / ".." / "transcript.md").write_text(_sample_transcript(frames), encoding="utf-8")
        count = render_composites(tmp_path / "transcript.md", frames, out)
        assert count == 3
        assert sorted(p.name for p in out.glob("*.png")) == [
            "composite_00.png",
            "composite_01.png",
            "composite_02.png",
        ]

    def test_composites_have_canvas_size(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        out = tmp_path / "composite"
        (tmp_path / "transcript.md").write_text(_sample_transcript(frames), encoding="utf-8")
        render_composites(tmp_path / "transcript.md", frames, out)
        for png in out.glob("*.png"):
            with Image.open(png) as img:
                assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    def test_sap_frame_is_fitted_not_stretched(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        out = tmp_path / "composite"
        # A frame whose aspect ratio cannot fill the SAP panel exactly:
        _write_frame(frames / "02_easy_access.png", size=(400, 1000))
        transcript = (
            "[beat 2] role=assistant frame=frames/02_easy_access.png\nLogging into the dev system…\ntool=sap_login\n"
        )
        (tmp_path / "transcript.md").write_text(transcript, encoding="utf-8")
        render_composites(tmp_path / "transcript.md", frames, out)
        with Image.open(out / "composite_02.png") as img:
            sap_pixel = img.getpixel((CANVAS_WIDTH - 10, CANVAS_HEIGHT // 2))
            # Letterboxed area must be the panel background, not stretched pixels
            assert sap_pixel == BACKGROUND

    def test_chat_shows_current_beat_message(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        out = tmp_path / "composite"
        _write_frame(frames / "02_easy_access.png")
        transcript = (
            "[beat 0] role=user\n"
            "Create business partner Max Mustermann.\n"
            "\n"
            "[beat 1] role=assistant frame=frames/02_easy_access.png\n"
            "Logging into the dev system…\n"
            "tool=sap_login\n"
        )
        (tmp_path / "transcript.md").write_text(transcript, encoding="utf-8")
        render_composites(tmp_path / "transcript.md", frames, out)

        def chat_ink_rows(name: str) -> int:
            with Image.open(out / name) as img:
                px = img.convert("RGB")
                return sum(
                    1
                    for y in range(TITLE_HEIGHT + 1, CANVAS_HEIGHT)
                    if any(px.getpixel((x, y)) != BACKGROUND for x in range(10, CHAT_WIDTH - 10, 8))
                )

        # The user bubble must appear in its own composite, not only the next one.
        assert chat_ink_rows("composite_00.png") > 0
        assert chat_ink_rows("composite_01.png") > chat_ink_rows("composite_00.png")

    def test_chat_panel_holds_accumulated_history(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        out = tmp_path / "composite"
        # Skip the title beat here: the title card dims the whole canvas and
        # would pollute the ink measurement. Compare plain chat beats instead.
        transcript = _sample_transcript(frames).replace(
            "[beat 0] role=title\nSAP GUI MCP — chat with Claude, watch SAP do the work\n\n",
            "",
        )
        (tmp_path / "transcript.md").write_text(transcript, encoding="utf-8")
        render_composites(tmp_path / "transcript.md", frames, out)

        def chat_ink_rows(name: str) -> int:
            with Image.open(out / name) as img:
                px = img.convert("RGB")
                return sum(
                    1
                    for y in range(CANVAS_HEIGHT)
                    if any(px.getpixel((x, y)) != BACKGROUND for x in range(10, CHAT_WIDTH - 10, 8))
                )

        # Beat 2 renders both messages; beat 1 renders one.
        assert chat_ink_rows("composite_01.png") < chat_ink_rows("composite_02.png")

    def test_final_beat_message_visible_with_scrolling(self, tmp_path: Path) -> None:
        """With 10 storyboard beats and a big font, the last bubble must still show."""
        frames = tmp_path / "frames"
        frames.mkdir()
        _write_frame(frames / "02_easy_access.png")
        out = tmp_path / "composite"
        # Eleven messages exceed the panel height even at default font size.
        blocks: list[str] = []
        for i in range(1, 12):
            blocks.append(
                f"[beat {i}] role=assistant frame=frames/02_easy_access.png\n"
                f"Step number {i} of this long demo narrative.\n"
                "tool=sap_login"
            )
        transcript = "\n\n".join(blocks) + "\n"
        (tmp_path / "transcript.md").write_text(transcript, encoding="utf-8")
        render_composites(tmp_path / "transcript.md", frames, out)
        # The newest message text must appear in the final composite.
        with Image.open(out / "composite_11.png") as img:
            # crude assertion: the bottom third of the chat panel must contain
            # ink (the newest bubble is drawn last at the bottom)
            px = img.convert("RGB")
            bottom = [
                (x, y)
                for y in range(CANVAS_HEIGHT - 120, CANVAS_HEIGHT - 20)
                for x in range(10, CHAT_WIDTH - 10, 4)
                if px.getpixel((x, y)) != BACKGROUND
            ]
            assert bottom, "Newest bubble missing from the bottom of the chat panel"

    def test_deterministic_output(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        (tmp_path / "transcript.md").write_text(_sample_transcript(frames), encoding="utf-8")
        out1, out2 = tmp_path / "c1", tmp_path / "c2"
        render_composites(tmp_path / "transcript.md", frames, out1)
        render_composites(tmp_path / "transcript.md", frames, out2)
        for png1 in sorted(out1.glob("*.png")):
            png2 = out2 / png1.name
            assert png1.read_bytes() == png2.read_bytes(), f"{png1.name} differs between runs"

    def test_oversized_bubble_raises(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        (tmp_path / "transcript.md").write_text(
            "[beat 2] role=assistant\n" + "unbreakable " * 100 + "\n",
            encoding="utf-8",
        )
        with pytest.raises(RenderError, match="taller than the chat panel"):
            render_composites(tmp_path / "transcript.md", frames, tmp_path / "composite")

    def test_empty_transcript_raises(self, tmp_path: Path) -> None:
        (tmp_path / "transcript.md").write_text("", encoding="utf-8")
        with pytest.raises(RenderError, match="no beats"):
            render_composites(tmp_path / "transcript.md", tmp_path / "frames", tmp_path / "composite")

    def test_checkmark_only_message_renders(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        _write_frame(frames / "02_easy_access.png")
        out = tmp_path / "composite"
        (tmp_path / "transcript.md").write_text(
            "[beat 1] role=assistant frame=frames/02_easy_access.png\n✓\n",
            encoding="utf-8",
        )
        render_composites(tmp_path / "transcript.md", frames, out)
        assert (out / "composite_01.png").exists()

    def test_missing_frame_file_fails_loudly(self, tmp_path: Path) -> None:
        (tmp_path / "transcript.md").write_text(
            "[beat 2] role=assistant frame=frames/nope.png\nHi there this is long enough\n",
            encoding="utf-8",
        )
        with pytest.raises(RenderError, match=r"nope\.png"):
            render_composites(tmp_path / "transcript.md", tmp_path / "frames", tmp_path / "composite")

    def test_emits_concat_file_with_durations(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        (tmp_path / "transcript.md").write_text(_sample_transcript(frames), encoding="utf-8")
        out = tmp_path / "composite"
        render_composites(tmp_path / "transcript.md", frames, out)
        concat = out / "concat.txt"
        assert concat.exists()
        lines = concat.read_text(encoding="utf-8").strip().splitlines()
        # ffmpeg concat demuxer format: `file 'X'` and `duration T` on
        # separate lines, plus a final repeat of the last file line (ffmpeg
        # otherwise ignores the last duration).
        assert len(lines) == 2 * 3 + 1  # 3 beats times (file + duration) + trailing repeat
        assert lines[0] == "file 'composite_00.png'"
        assert lines[1].startswith("duration ")
        assert lines[-1] == "file 'composite_02.png'"


class TestCard:
    def test_card_has_transparent_margin_and_rounded_corners(self, tmp_path: Path) -> None:
        frames = tmp_path / "frames"
        frames.mkdir()
        _write_frame(frames / "02_easy_access.png")
        (tmp_path / "transcript.md").write_text(
            "[beat 1] role=assistant frame=frames/02_easy_access.png\nLogging in…\ntool=sap_login\n", encoding="utf-8"
        )
        render_composites(tmp_path / "transcript.md", frames, tmp_path / "out", card=True)
        with Image.open(tmp_path / "out" / "composite_01.png") as img:
            assert img.mode == "RGBA"
            assert img.size == (CANVAS_WIDTH + 2 * OUTER_MARGIN, CANVAS_HEIGHT + 2 * OUTER_MARGIN)
            assert img.getpixel((0, 0))[3] == 0  # margin
            assert img.getpixel((OUTER_MARGIN + 1, OUTER_MARGIN + 1))[3] == 0  # rounded corner is cut off
            assert img.getpixel((img.width // 2, OUTER_MARGIN + 20))[3] == 255  # card body
            alphas = {img.getpixel((x, y))[3] for x in range(img.width) for y in range(img.height)}
            assert alphas == {0, 255}  # GIF transparency is binary: no semi-transparent halo pixels
