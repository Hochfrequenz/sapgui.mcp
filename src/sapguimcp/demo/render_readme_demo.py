"""README demo renderer: parses the demo transcript and renders composite frames.

The readme-demo skill (`.claude/skills/readme-demo/SKILL.md`) produces a
transcript sidecar plus beat-numbered SAP screenshots during a real run; this
module deterministically composites them into one PNG per storyboard beat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Canvas constants (spec: docs/superpowers/specs/2026-10-06-readme-demo-design.md)
CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 640
CHAT_WIDTH = 480
PADDING = 24

VALID_ROLES = frozenset({"user", "assistant", "title"})

_BEAT_HEADER = re.compile(r"^\[beat (?P<num>\d+)\](?P<keys>.*)$")
_KEY_VALUE = re.compile(r"(?P<key>\w+)=(?P<value>\S+)")


class ParseError(ValueError):
    """Raised when a transcript does not conform to the sidecar format."""


@dataclass(frozen=True)
class Beat:
    """One chat beat: a message, optionally with a tool chip and a frame."""

    number: int
    role: str
    message: str
    tool: str | None = None
    frame: str | None = None


def parse_transcript(text: str) -> list[Beat]:
    """Parse the transcript sidecar format into an ordered list of beats.

    Format: one block per beat, starting with ``[beat N]`` followed by optional
    space-separated ``key=value`` pairs (``role``, ``frame``; unknown keys are
    rejected), then a non-empty message body with an optional trailing ``tool=``
    line (the tool chip may appear anywhere in the block after the header; user
    beats may not have one).
    """
    beats: list[Beat] = []
    seen: set[int] = set()
    for block in re.split(r"\n\s*\n", text.strip()):
        if not block:
            continue
        lines = block.splitlines()
        header = _BEAT_HEADER.match(lines[0])
        if header is None:
            raise ParseError(f"Block does not start with [beat N]: {lines[0]!r}")
        number = int(header.group("num"))
        if number in seen:
            raise ParseError(f"Duplicate beat number: {number}")
        seen.add(number)

        role: str | None = None
        frame: str | None = None
        keys = header.group("keys")
        for match in _KEY_VALUE.finditer(keys):
            if match.group("key") == "role":
                role = match.group("value")
            elif match.group("key") == "frame":
                frame = match.group("value")
            elif match.group("key") == "tool":
                raise ParseError(
                    f"Beat {number}: tool= cannot be a header key; it must be on its own line after the message"
                )
            else:
                raise ParseError(f"Beat {number} has unknown header key {match.group('key')!r} in {lines[0]!r}")
        residue = _KEY_VALUE.sub("", keys).strip()
        if residue:
            raise ParseError(f"Beat {number} has unparsable header text {residue!r} in {lines[0]!r}")
        if role is None:
            raise ParseError(f"Beat {number} is missing role=")
        if role not in VALID_ROLES:
            raise ParseError(f"Beat {number} has unknown role={role!r} (valid: {sorted(VALID_ROLES)})")

        tool: str | None = None
        message_lines: list[str] = []
        for line in lines[1:]:
            if line.startswith("tool="):
                if role == "user":
                    raise ParseError(f"Beat {number}: user beats cannot carry a tool= chip")
                tool = line[len("tool=") :].strip() or None
            else:
                message_lines.append(line)
        message = "\n".join(message_lines).strip()
        if not message:
            raise ParseError(f"Beat {number} has an empty message")
        beats.append(Beat(number=number, role=role, message=message, tool=tool, frame=frame))
    return beats


# Layout constants (spec Layout section; panels fill the canvas)
SAP_WIDTH = CANVAS_WIDTH - CHAT_WIDTH
TITLE_HEIGHT = 48
BACKGROUND = (250, 251, 253)
PANEL_BORDER = (210, 214, 220)
INK = (28, 30, 33)
MUTED = (120, 124, 130)
USER_BUBBLE = (222, 235, 255)
ASSISTANT_BUBBLE = (240, 241, 244)
TITLE_BG = (23, 26, 33)
TITLE_FG = (245, 246, 248)
SAP_PANEL_BG = (255, 255, 255)
SUCCESS_GREEN = (67, 160, 71)

# Spec: chat text must be ≥14px effective at GitHub's ~880px GIF render width.
# 880/1280 = 0.6875, so canvas-scale fonts must be ≥ 14/0.6875 ≈ 20.4 → 22px.
FONT_SIZE = 22
TOOL_FONT_SIZE = 17
TITLE_FONT_SIZE = 26


class RenderError(ValueError):
    """Raised when rendering cannot proceed (e.g. a frame file is missing)."""


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default(size)  # type: ignore[return-value]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_composites(transcript_path: Path, frames_dir: Path, out_dir: Path) -> int:
    """Render one composite PNG per beat plus an ffmpeg concat file.

    *frames_dir* is the directory the transcript's ``frame=`` paths are
    relative to (``frames/`` inside the readme-demo workdir). Returns the
    number of beats rendered.
    """
    beats = parse_transcript(transcript_path.read_text(encoding="utf-8"))
    if not beats:
        raise RenderError("Transcript contains no beats")
    out_dir.mkdir(parents=True, exist_ok=True)

    title_font = _font(TITLE_FONT_SIZE)
    body_font = _font(FONT_SIZE)
    tool_font = _tool_font(TOOL_FONT_SIZE)

    bubble_history: list[Beat] = []
    concat_lines: list[str] = []
    last_frame_path: Path | None = None
    last_composite_name: str | None = None

    for beat in beats:
        if beat.frame is not None:
            candidate = frames_dir / Path(beat.frame).name
            if not candidate.exists():
                raise RenderError(f"Frame file not found: {candidate}")
            last_frame_path = candidate

        # The current beat's bubble belongs to its own composite: the spec wants
        # "full chat history so far" alongside the current frame.
        bubble_history.append(beat)

        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BACKGROUND)
        draw = ImageDraw.Draw(canvas)
        _draw_title(draw, title_font)
        _draw_chat(draw, bubble_history, body_font, tool_font)
        _draw_sap(draw, canvas, last_frame_path)
        if beat.role == "title":
            # Title card: dim the panels (chat + SAP), show the title centered.
            _draw_title_card(canvas, title_font)

        composite_name = f"composite_{beat.number:02d}.png"
        canvas.save(out_dir / composite_name)
        last_composite_name = composite_name
        # ffmpeg concat demuxer: `duration` must be its own line AFTER `file`,
        # and ffmpeg drops the last duration unless the last file is repeated.
        concat_lines.append(f"file '{composite_name}'")
        concat_lines.append(f"duration {_beat_seconds(beat)}")

    if last_composite_name is not None:
        concat_lines.append(f"file '{last_composite_name}'")

    (out_dir / "concat.txt").write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    return len(beats)


# Per-beat display duration in seconds, tuned once during production.
_BEAT_SECONDS_DEFAULT = 3.0
_BEAT_SECONDS_TITLE = 2.5
_BEAT_SECONDS_HOLD = 4.0  # beats whose message contains ✓ hold longer


def _beat_seconds(beat: Beat) -> float:
    if beat.role == "title":
        return _BEAT_SECONDS_TITLE
    if "✓" in beat.message:
        return _BEAT_SECONDS_HOLD
    return _BEAT_SECONDS_DEFAULT


def _tool_font(size: int) -> ImageFont.FreeTypeFont:
    return _font(size)


def _draw_title(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> None:
    draw.rectangle([0, 0, CANVAS_WIDTH, TITLE_HEIGHT], fill=TITLE_BG)
    draw.text(
        (PADDING, TITLE_HEIGHT // 2),
        "SAP GUI MCP — chat with Claude, watch SAP do the work",
        font=font,
        fill=TITLE_FG,
        anchor="lm",
    )


def _draw_title_card(canvas: Image.Image, font: ImageFont.FreeTypeFont) -> None:
    overlay = Image.new("RGB", canvas.size, TITLE_BG)
    blended = Image.blend(canvas, overlay, 0.85)
    canvas.paste(blended)
    draw = ImageDraw.Draw(canvas)
    text = "SAP GUI MCP"
    sub = "chat with Claude — watch SAP do the work"
    sub_font = _font(16)
    text_x = (CANVAS_WIDTH - draw.textlength(text, font=font)) // 2
    sub_x = (CANVAS_WIDTH - draw.textlength(sub, font=sub_font)) // 2
    draw.text((text_x, CANVAS_HEIGHT // 2 - 30), text, font=font, fill=TITLE_FG)
    draw.text((sub_x, CANVAS_HEIGHT // 2 + 10), sub, font=sub_font, fill=(160, 165, 175))


def _measure_bubble(
    draw: ImageDraw.ImageDraw,
    beat: Beat,
    body_font: ImageFont.FreeTypeFont,
    tool_font: ImageFont.FreeTypeFont,
    max_text_width: int,
) -> tuple[int, int, list[str], bool]:
    """Return (width, height, wrapped lines, has_checkmark) for a beat's bubble.

    ``✓`` has no glyph in the canvas fonts (it renders as tofu), so it is
    stripped from the text here and drawn as two line segments by ``_draw_chat``.
    """
    has_checkmark = "✓" in beat.message
    text = beat.message.replace("✓", "").strip() if has_checkmark else beat.message
    # Line 0 is indented 20px for the checkmark, so wrap everything narrower to keep it inside the bubble.
    lines = _wrap(draw, text, body_font, max_text_width - (20 if has_checkmark else 0))
    if not lines:
        # A message can strip down to nothing (e.g. it was only "✓"); keep one
        # empty line so the bubble still renders with its green checkmark.
        lines = [""]
    line_h = int(body_font.size) + 6
    height = len(lines) * line_h + 2 * 10 + (18 if beat.tool else 0)
    text_width = max(draw.textlength(ln, font=body_font) for ln in lines) + (
        20 if has_checkmark else 0  # line 0 is indented for the checkmark
    )
    if beat.tool:
        # The tool chip is drawn after a 14px triangle gutter; a short message
        # ("Saving…") must not leave it sticking out of the bubble.
        text_width = max(text_width, 14 + draw.textlength(beat.tool, font=tool_font))
    width = int(min(CHAT_WIDTH - 2 * PADDING, text_width + 2 * 12))
    return width, height, lines, has_checkmark


def _draw_chat(
    draw: ImageDraw.ImageDraw,
    history: list[Beat],
    body_font: ImageFont.FreeTypeFont,
    tool_font: ImageFont.FreeTypeFont,
) -> None:
    top = TITLE_HEIGHT + PADDING
    bottom_limit = CANVAS_HEIGHT - PADDING
    max_text_width = CHAT_WIDTH - 2 * PADDING - 16

    # Measure all bubbles first; if they overflow the panel, drop the OLDEST
    # ones until everything fits (scrolling: the newest message must stay
    # visible — it is the current step of the story).
    measured = [
        (beat, *_measure_bubble(draw, beat, body_font, tool_font, max_text_width))
        for beat in history
        if beat.role != "title"
    ]
    gap = 10
    while measured:
        total_h = sum(h for _, _, h, _, _ in measured) + gap * (len(measured) - 1)
        if total_h <= bottom_limit - top:
            break
        measured.pop(0)
    if not measured and any(beat.role != "title" for beat in history):
        # Only the title role is filtered out above, so an empty list here means
        # even the newest bubble alone does not fit the panel.
        raise RenderError(
            f"Chat bubble for beat {history[-1].number} is taller than the chat panel — shorten the message"
        )

    y = top + max(0, bottom_limit - top - (sum(h for _, _, h, _, _ in measured) + gap * (len(measured) - 1)))
    for beat, width, height, lines, has_checkmark in measured:
        fill = USER_BUBBLE if beat.role == "user" else ASSISTANT_BUBBLE
        draw.rounded_rectangle(
            [PADDING, y, PADDING + width, y + height],
            radius=10,
            fill=fill,
            outline=PANEL_BORDER,
        )
        ty = y + 8
        line_h = int(body_font.size) + 6
        for i, ln in enumerate(lines):
            text_x = PADDING + 12
            if has_checkmark and i == 0:
                # "✓" from the transcript, drawn as line segments: the canvas
                # fonts have no glyph for it (it would render as tofu).
                mid_y = ty + line_h // 2
                draw.line([(text_x + 2, mid_y), (text_x + 6, mid_y + 5)], fill=SUCCESS_GREEN, width=3)
                draw.line([(text_x + 6, mid_y + 5), (text_x + 14, mid_y - 6)], fill=SUCCESS_GREEN, width=3)
                text_x += 20
            draw.text((text_x, ty), ln, font=body_font, fill=INK)
            ty += line_h
        if beat.tool:
            # "▸" from the sketch has no glyph either: draw a small triangle
            # instead and shift the tool text right of it.
            tri_x = PADDING + 12
            tri_y = ty + 2 + line_h // 2
            draw.polygon(
                [(tri_x, tri_y - 5), (tri_x, tri_y + 5), (tri_x + 8, tri_y)],
                fill=MUTED,
            )
            draw.text((tri_x + 14, ty + 2), beat.tool, font=tool_font, fill=MUTED)
        y += height + gap


def _draw_sap(draw: ImageDraw.ImageDraw, canvas: Image.Image, frame_path: Path | None) -> None:
    x0 = CHAT_WIDTH
    draw.rectangle([x0, TITLE_HEIGHT, CANVAS_WIDTH, CANVAS_HEIGHT], fill=SAP_PANEL_BG)
    draw.line([(x0 - 1, TITLE_HEIGHT), (x0 - 1, CANVAS_HEIGHT)], fill=PANEL_BORDER)
    if frame_path is None:
        return
    with Image.open(frame_path) as img:
        frame = img.convert("RGB")
    avail_w = SAP_WIDTH - 2 * PADDING
    avail_h = CANVAS_HEIGHT - TITLE_HEIGHT - 2 * PADDING
    scale = min(avail_w / frame.width, avail_h / frame.height)
    new_size = (max(1, int(frame.width * scale)), max(1, int(frame.height * scale)))
    frame = frame.resize(new_size, Image.Resampling.LANCZOS)
    fx = x0 + (SAP_WIDTH - new_size[0]) // 2
    fy = TITLE_HEIGHT + (avail_h - new_size[1]) // 2 + PADDING
    canvas.paste(frame, (fx, fy))


def main() -> int:
    """CLI: render composites from a readme-demo working directory."""
    import argparse  # noqa: PLC0415 -- CLI entry point only, keeps module import cheap

    parser = argparse.ArgumentParser(description="Render README demo composites")
    parser.add_argument("--workdir", type=Path, default=Path("readme-demo"), help="readme-demo working directory")
    args = parser.parse_args()
    frames = args.workdir / "frames"
    out = args.workdir / "composite"
    count = render_composites(args.workdir / "transcript.md", frames, out)
    print(f"Rendered {count} composites to {out}")
    print("Encode the GIF with (see scripts/README.md for the full command):")
    print(f"  ffmpeg -f concat -safe 0 -i {out / 'concat.txt'} -vf <filter> out.gif")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
