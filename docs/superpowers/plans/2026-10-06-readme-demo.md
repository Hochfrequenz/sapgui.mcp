# README Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `readme-demo` skill (tracked, dual-purpose) plus the deterministic GIF pipeline (transcript parser, layout engine, assembler, ffmpeg docs) so a real run against the test system produces the README demo GIF.

**Architecture:** A committed SKILL.md choreographs a real agent run (login → BP create → screenshot → SE16 verify) and appends chat beats to a `transcript.md` sidecar while capturing beat-numbered SAP screenshots. A pure-Python renderer (`scripts/render_readme_demo.py`) parses the transcript, lays out chat bubbles + tool chips on the left and SAP frames on the right of a fixed 1280×640 canvas, and emits one composite PNG per beat plus an ffmpeg concat file. A documented ffmpeg command turns composites into the GIF. The skill contains the full BP flow inline (distilled from an internal recipe; no private repo names in committed files).

**Tech Stack:** Python 3.11+, Pillow (pinned in the `tests` dependency group), pytest, ruff, mypy `--strict`, ffmpeg (external, documented), Claude Code/Desktop project skill format.

Spec: `docs/superpowers/specs/2026-10-06-readme-demo-design.md`

---

## File Structure

| File | Action | Responsibility |
| --- | --- | --- |
| `.gitignore` | Modify | Glob-form `.claude/*` recipe (skill trackable, rest ignored) + `/readme-demo/` working dir |
| `.claude/skills/readme-demo/SKILL.md` | Create | The committed demo skill: trigger phrases, inline BP flow, transcript writing, per-beat screenshot capture, SE16 verification |
| `src/sapguimcp/demo/__init__.py` | Create | Package marker (importable by unittests without path hacks) |
| `src/sapguimcp/demo/render_readme_demo.py` | Create | Transcript parser + layout renderer + assembler entry point (single module: parser and layout share the `Beat` dataclass; ~300 lines, cohesive) |
| `unittests/test_readme_demo_transcript.py` | Create | Parser tests (keys, repeats, malformed input) |
| `unittests/test_readme_demo_render.py` | Create | Renderer tests (canvas math, bubble layout, composite count, determinism) |
| `scripts/render_readme_demo.py` | Create | 3-line shim importing and calling `sapguimcp.demo.render_readme_demo.main()` (matches scripts/ being dev-only wrappers) |
| `scripts/README.md` | Modify | Document the renderer + the exact ffmpeg GIF command |
| `pyproject.toml` | Modify | Add `pillow` to the `tests` dependency group (pinned) |
| `README.md` | Modify | Embed the GIF placeholder + "run this demo yourself" note (GIF file added in Task 6) |

Deliberately **not** created: a `docs/` copy of the skill, a config-driven layout file (YAGNI — one canvas, constants in the module), a Python GIF encoder (ffmpeg does palette better).

Conventions: ruff line-length 120, mypy strict on `src/`, unittests run offline via `uv run --locked --group tests python -m pytest` (testpaths is `unittests/`), commit style is conventional (`feat:`, `docs:`, `chore:`), no SAP hostnames/SIDs in committed files (system IDs visible in the *screenshots* are waived by the maintainer; that waiver does not extend to prose). Follow the memory rule: run only the tests relevant to the task (`pytest -k readme_demo`), not the whole suite.

---

## Task 1: Gitignore recipe + dependency group

**Files:**
- Modify: `.gitignore` (line 104, `.claude/`)
- Modify: `pyproject.toml` (dependency-groups, `tests`)

- [ ] **Step 1: Switch `.claude/` ignore to glob form and add the working dir**

In `.gitignore`, replace the line

```
.claude/
```

with

```gitignore
.claude/*
!.claude/skills/
.claude/skills/*
!.claude/skills/readme-demo/
/readme-demo/
```

(Rationale: git cannot re-include a path whose parent directory is excluded in directory form — a plain `!.claude/skills/` under `.claude/` is silently dead. Glob form re-enables exactly one skill. `/readme-demo/` is the run working dir: transcripts, frames, composites never get committed.)

- [ ] **Step 2: Verify the ignore behavior**

```bash
mkdir -p .claude/worktrees .claude/skills/readme-demo .claude/skills/other-skill
touch .claude/skills/readme-demo/SKILL.md .claude/skills/other-skill/SKILL.md
git check-ignore -v .claude/worktrees/x .claude/skills/other-skill/SKILL.md; echo "exit=$?"
git status --porcelain --untracked-files=all | grep -E "SKILL.md|readme-demo"
```

Expected: `git check-ignore` lists the worktrees and other-skill paths (exit 0), and `git status` shows **only** `.claude/skills/readme-demo/SKILL.md` as untracked. Clean up the scratch dirs afterwards (`rm -rf .claude/skills/other-skill .claude/worktrees/x` — keep `readme-demo/`).

- [ ] **Step 3: Add Pillow to the tests group**

In `pyproject.toml`, `tests = [...]` becomes:

```toml
tests = [
    "pytest==9.1.1",
    "anyio==4.15.1",  # includes pytest-anyio plugin for proper async fixture teardown
    "python-dotenv>=1.0.0",
    "beautifulsoup4==4.15.0",  # HTML parsing for selector unit tests
    "lxml==6.1.3",  # Fallback parser for Python 3.13+ (html.parser has stricter nesting rules)
    "respx==0.23.1",  # Mock httpx requests in tests
    "pillow==12.1.1",  # README demo renderer (unittests test canvas layout math)
]
```

Pin to 12.1.1 (the version already present in the dev environment; keeps `uv run --locked` reproducible — the lockfile update lands in the next step).

- [ ] **Step 4: Sync the lockfile and verify offline tests still run**

```bash
uv lock
uv run --locked --group tests python -c "from PIL import Image; print('pillow ok')"
uv run --locked --group tests python -m pytest unittests/test_aria_snapshot_type.py -q
```

Expected: `pillow ok`, and the existing offline test passes (confirms the lock update didn't break the pinned env).

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml uv.lock
git commit -m "chore: make .claude/skills/readme-demo trackable and add pillow to tests group"
```

---

## Task 2: Transcript parser

**Files:**
- Create: `src/sapguimcp/demo/__init__.py`
- Create: `src/sapguimcp/demo/render_readme_demo.py` (parser part)
- Test: `unittests/test_readme_demo_transcript.py`

- [ ] **Step 1: Write the failing tests**

Create `unittests/test_readme_demo_transcript.py`:

```python
"""Tests for the readme-demo transcript parser (renderer input)."""

import textwrap

import pytest

from sapguimcp.demo.render_readme_demo import Beat, ParseError, parse_transcript


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
        assert beats[0].message == "Log into the dev system, create business partner\nMax Mustermann, and verify in SE16."
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run --locked --group tests python -m pytest unittests/test_readme_demo_transcript.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sapguimcp.demo'`.

- [ ] **Step 3: Implement the parser**

Create `src/sapguimcp/demo/__init__.py` (empty) and `src/sapguimcp/demo/render_readme_demo.py`:

```python
"""README demo renderer: parses the demo transcript and renders composite frames.

The readme-demo skill (`.claude/skills/readme-demo/SKILL.md`) produces a
transcript sidecar plus beat-numbered SAP screenshots during a real run; this
module deterministically composites them into one PNG per storyboard beat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canvas constants (spec: docs/superpowers/specs/2026-10-06-readme-demo-design.md)
CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 640
CHAT_WIDTH = 480
PADDING = 24

VALID_ROLES = frozenset({"user", "assistant", "title"})

_BEAT_HEADER = re.compile(r"^\[beat (?P<num>\d+)\](?P<keys>.*)$")
_KEY_VALUE = re.compile(r"(?P<key>role|frame|tool)=(?P<value>\S+)")


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
    space-separated ``key=value`` pairs (``role``, ``frame``), then a non-empty
    message body with an optional trailing ``tool=`` line (the tool chip may
    appear anywhere in the block after the header; user beats may not have one).
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
        for match in _KEY_VALUE.finditer(header.group("keys")):
            if match.group("key") == "role":
                role = match.group("value")
            elif match.group("key") == "frame":
                frame = match.group("value")
            else:
                raise ParseError(f"Unknown header key in {lines[0]!r}")
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run --locked --group tests python -m pytest unittests/test_readme_demo_transcript.py -v
```

Expected: 10 PASS.

- [ ] **Step 5: Lint and type-check the new module**

```bash
uv run --locked --group linting ruff check src/sapguimcp/demo unittests/test_readme_demo_transcript.py
uv run --locked --group linting ruff format src/sapguimcp/demo unittests/test_readme_demo_transcript.py
uv run --locked --group type_check mypy --strict src/sapguimcp/demo
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/demo unittests/test_readme_demo_transcript.py
git commit -m "feat(readme-demo): transcript sidecar parser"
```

---

## Task 3: Layout renderer and assembler

**Files:**
- Modify: `src/sapguimcp/demo/render_readme_demo.py` (renderer part)
- Test: `unittests/test_readme_demo_render.py`

- [ ] **Step 1: Write the failing tests**

Create `unittests/test_readme_demo_render.py`:

```python
"""Tests for the readme-demo composite renderer (layout + assembler)."""

from pathlib import Path

import pytest
from PIL import Image

from sapguimcp.demo.render_readme_demo import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CHAT_WIDTH,
    RenderError,
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
            "[beat 2] role=assistant frame=frames/02_easy_access.png\n"
            "Logging into the dev system…\n"
            "tool=sap_login\n"
        )
        (tmp_path / "transcript.md").write_text(transcript, encoding="utf-8")
        render_composites(tmp_path / "transcript.md", frames, out)
        with Image.open(out / "composite_02.png") as img:
            sap_pixel = img.getpixel((CANVAS_WIDTH - 10, CANVAS_HEIGHT // 2))
            # Letterboxed area must be the panel background, not stretched pixels
            assert sap_pixel in ((255, 255, 255), (245, 246, 248))

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
                px = img.convert("L")
                return sum(
                    1
                    for y in range(CANVAS_HEIGHT)
                    if any(px.getpixel((x, y)) < 200 for x in range(10, CHAT_WIDTH - 10, 8))
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
            px = img.convert("L")
            bottom = [
                (x, y)
                for y in range(CANVAS_HEIGHT - 120, CANVAS_HEIGHT - 20)
                for x in range(10, CHAT_WIDTH - 10, 4)
                if px.getpixel((x, y)) < 200
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run --locked --group tests python -m pytest unittests/test_readme_demo_render.py -q
```

Expected: FAIL with `ImportError: cannot import name 'render_composites'`.

- [ ] **Step 3: Implement the renderer**

Append to `src/sapguimcp/demo/render_readme_demo.py` (do **not** repeat the
`from __future__ import annotations` line — it is already at the top of the
module and a second one is a `SyntaxError`; the imports below merge into the
existing import block):

```python
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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
        bubble_history.append(beat)
        last_composite_name = composite_name
        # ffmpeg concat demuxer: `duration` must be its own line AFTER `file`,
        # and ffmpeg drops the last duration unless the last file is repeated.
        concat_lines.append(f"file '{composite_name}'")
        concat_lines.append(f"duration {_beat_seconds(beat)}")

    if last_composite_name is not None:
        concat_lines.append(f"file '{last_composite_name}'")

    (out_dir / "concat.txt").write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    return len(beats)
```

Then the drawing helpers (same module, private functions):

```python
# Per-beat display duration in seconds, tuned once during production.
_BEAT_SECONDS_DEFAULT = 3.0
_BEAT_SECONDS_TITLE = 2.5
_BEAT_SECONDS_HOLD = 4.0  # final beat holds longer


def _beat_seconds(beat: Beat) -> float:
    if beat.role == "title":
        return _BEAT_SECONDS_TITLE
    if "✓" in beat.message:
        return _BEAT_SECONDS_HOLD
    return _BEAT_SECONDS_DEFAULT
```

And a second helpers block (same module):

```python
def _tool_font(size: int) -> ImageFont.FreeTypeFont:
    return _font(size)


def _draw_title(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> None:
    draw.rectangle([0, 0, CANVAS_WIDTH, TITLE_HEIGHT], fill=TITLE_BG)
    draw.text((PADDING, 12), "SAP GUI MCP — chat with Claude, watch SAP do the work", font=font, fill=TITLE_FG)


def _draw_title_card(canvas: Image.Image, font: ImageFont.FreeTypeFont) -> None:
    overlay = Image.new("RGB", canvas.size, TITLE_BG)
    blended = Image.blend(canvas, overlay, 0.85)
    canvas.paste(blended)
    draw = ImageDraw.Draw(canvas)
    text = "SAP GUI MCP"
    sub = "chat with Claude — watch SAP do the work"
    draw.text((CANVAS_WIDTH // 2 - 120, CANVAS_HEIGHT // 2 - 30), text, font=font, fill=TITLE_FG)
    draw.text((CANVAS_WIDTH // 2 - 150, CANVAS_HEIGHT // 2 + 10), sub, font=_font(16), fill=(160, 165, 175))


def _measure_bubble(
    draw: ImageDraw.ImageDraw,
    beat: Beat,
    body_font: ImageFont.FreeTypeFont,
    max_text_width: int,
) -> tuple[int, int, list[str]]:
    """Return (width, height, wrapped lines) for a beat's bubble."""
    lines = _wrap(draw, beat.message, body_font, max_text_width)
    line_h = int(body_font.size) + 6
    height = len(lines) * line_h + 2 * 10 + (18 if beat.tool else 0)
    width = int(
        min(
            CHAT_WIDTH - 2 * PADDING,
            max(draw.textlength(ln, font=body_font) for ln in lines) + 2 * 12,
        )
    )
    return width, height, lines


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
        (beat, *_measure_bubble(draw, beat, body_font, max_text_width)) for beat in history if beat.role != "title"
    ]
    gap = 10
    while measured:
        total_h = sum(h for _, _, h, _ in measured) + gap * (len(measured) - 1)
        if total_h <= bottom_limit - top:
            break
        measured.pop(0)

    y = top + max(0, bottom_limit - top - (sum(h for _, _, h, _ in measured) + gap * (len(measured) - 1)))
    for beat, width, height, lines in measured:
        fill = USER_BUBBLE if beat.role == "user" else ASSISTANT_BUBBLE
        draw.rounded_rectangle(
            [PADDING, y, PADDING + width, y + height],
            radius=10,
            fill=fill,
            outline=PANEL_BORDER,
        )
        ty = y + 8
        line_h = int(body_font.size) + 6
        for ln in lines:
            draw.text((PADDING + 12, ty), ln, font=body_font, fill=INK)
            ty += line_h
        if beat.tool:
            draw.text((PADDING + 12, ty + 2), f"▸ {beat.tool}", font=tool_font, fill=MUTED)
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
```

And a CLI entry point at the end of the module:

```python
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
```

Note on the sketch: `import shutil` from earlier drafts is gone — the final
code above carries no unused imports. If ruff still flags anything, fix the
module, not the lint config.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run --locked --group tests python -m pytest unittests/test_readme_demo_render.py -v
```

Expected: 8 PASS. If `test_sap_frame_is_fitted_not_stretched` is flaky because of the letterbox color assertion, assert instead that the pixel at the panel corner equals `SAP_PANEL_BG` — the intent is "no stretched SAP pixels," not a specific gray.

- [ ] **Step 5: Lint and type-check**

```bash
uv run --locked --group linting ruff check src/sapguimcp/demo unittests/test_readme_demo_render.py
uv run --locked --group linting ruff format src/sapguimcp/demo unittests/test_readme_demo_render.py
uv run --locked --group type_check mypy --strict src/sapguimcp/demo
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/demo/render_readme_demo.py unittests/test_readme_demo_render.py
git commit -m "feat(readme-demo): composite renderer with chat/SAP layout"
```

---

## Task 4: Scripts shim, scripts/README.md ffmpeg docs, smoke-render a synthetic run

**Files:**
- Create: `scripts/render_readme_demo.py`
- Modify: `scripts/README.md`

- [ ] **Step 1: Create the shim**

`scripts/render_readme_demo.py`:

```python
"""Dev-only wrapper: render README demo composites (see scripts/README.md)."""

from sapguimcp.demo.render_readme_demo import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Document the workflow in scripts/README.md**

Add a section after the existing "Transaction Catalog Building" section:

```markdown
## README Demo GIF

The README GIF is produced from a real agent run by the `readme-demo` skill
(`.claude/skills/readme-demo/SKILL.md`). The skill writes `readme-demo/transcript.md`
and beat-numbered screenshots into `readme-demo/frames/`. To (re)build the composites
and the GIF:

```powershell
uv run --locked --group tests python scripts/render_readme_demo.py --workdir readme-demo
ffmpeg -f concat -safe 0 -i readme-demo/composite/concat.txt \
  -vf "fps=10,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  readme-demo.gif
```

Copy `readme-demo.gif` to `docs/readme-demo.gif` and commit it. The GIF is a
re-timed composite of a real run — real messages, real screenshots; only the
pacing is edited (see the spec's honesty note).
```

- [ ] **Step 3: Smoke-render a synthetic run end to end (not committed)**

Use a repo-relative working dir (under the already-ignored `readme-demo/`) —
`/tmp` paths break on Windows because MSYS does not convert paths embedded in
`python -c` strings, and the write would land in `C:\tmp` while the bash
heredoc wrote to the user temp dir:

```bash
mkdir -p readme-demo/smoke/frames
cat > readme-demo/smoke/transcript.md <<'EOF'
[beat 0] role=title
SAP GUI MCP — chat with Claude, watch SAP do the work

[beat 1] role=user
Log into the dev system, create business partner Max Mustermann, save it, take a screenshot, and verify in SE16.

[beat 2] role=assistant frame=frames/02_easy_access.png
Logging into the dev system…
tool=sap_login
EOF
uv run --locked --group tests python -c "
from PIL import Image
Image.new('RGB', (1024, 768), '#1b3a5c').save('readme-demo/smoke/frames/02_easy_access.png')
"
uv run --locked --group tests python scripts/render_readme_demo.py --workdir readme-demo/smoke
```

Expected: "Rendered 3 composites" and the ffmpeg hint. Open
`readme-demo/smoke/composite/composite_02.png` and eyeball it: title bar,
chat history with user + assistant bubble + muted `▸ sap_login` chip, SAP
frame centered right. Delete `readme-demo/smoke/` afterwards (it is inside
the ignored workdir, but keep the area clean for the real run).

- [ ] **Step 4: Run the relevant tests once more and lint the shim**

```bash
uv run --locked --group tests python -m pytest -k readme_demo -q
uv run --locked --group linting ruff check scripts/render_readme_demo.py
```

Expected: all PASS, no lint errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/render_readme_demo.py scripts/README.md
git commit -m "feat(readme-demo): scripts shim and GIF encode docs"
```

---

## Task 5: The skill itself

**Files:**
- Create: `.claude/skills/readme-demo/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `.claude/skills/readme-demo/SKILL.md`:

````markdown
---
name: readme-demo
description: >
  End-to-end demo of this MCP server for the project README and for users who
  want to see it in action: log into an SAP system, create a business partner
  (Max Mustermann by default), save it with Ctrl+S, capture a screenshot for
  the documentation, and verify the partner in SE16 (table BUT000). Use when
  the user says "run the readme demo", "demo the SAP MCP server", or invokes
  /readme-demo. Announce each step in one short chat sentence so the run reads
  as a story, and capture a numbered screenshot after every SAP-visible step.
---

# README Demo

You are demonstrating this MCP server end to end. The run produces two things:
a readable chat story (the sentences you say between steps) and the artifacts
that prove the work (screenshots, transcript).

**Work directory:** `/readme-demo/` (repo-root-relative, git-ignored). Create
it if missing. It receives `transcript.md` and `frames/`.

**Data:** use obviously fake data — first name `Max`, last name `Mustermann`
(unless the user passed other values), street `Teststraße 1`, postal code
`12345`, city `Testhausen`, country `DE`. Never use real personal data.

**Optional arguments:** partner first/last name, address, system key
(default: the default system in `systems.json`).

## How to run the demo

Work through the beats below. For every beat:

1. Say one short chat sentence announcing what you are about to do (plain
   language, no JSON, no internal jargon — the reader is a first-time user).
2. Call the tool.
3. If the beat captures a frame (see the list), call `sap_screenshot` and save
   the image to the named file under `readme-demo/frames/`.
4. Append the beat to `readme-demo/transcript.md` in the sidecar format
   below. `tool=` names the tool you just called; `frame=` references the
   screenshot file (relative to `readme-demo/`), when the beat has one.

Do not add artificial waits between steps. Pacing happens later at GIF
assembly time, outside this skill.

### How to capture frames (important)

`sap_screenshot` returns the picture to *you* (the agent sees it) but cannot
save it to disk. To write a frame file, use `sap_run_script` (desktop backend)
with the COM `hard_copy` call — the same way the server itself implements
screenshots. Absolute path required:

```python
# via sap_run_script, one shot per frame:
wnd = session.find_by_id("wnd[0]")
wnd.hard_copy(r"C:\<absolute path to repo>\readme-demo\frames\03_bp_initial.png", 2)
output("frame saved")
```

(`2` = PNG. `open()`/`import` are sandbox-blocked, but the injected
`session` object writes the file through COM — no `open()` needed. Verify the
absolute path form on the first live frame before proceeding with the run.)

### Beats

| Beat | Say | Do | Frame (if any) |
| --- | --- | --- | --- |
| 1 | State the whole task in one sentence. | — (no tool call; this is the user prompt you received) | — |
| 2 | "Logging into the dev system…" | `sap_login(system_key=…)` | `frames/02_easy_access.png` |
| 3 | "Opening transaction BP…" | `sap_transaction(tcode="bp")` | `frames/03_bp_initial.png` |
| 4 | "Creating a person…" | `sap_press_key(key="F5")` (confirm a type popup with `sap_press_key(key="Enter")` if one appears) | `frames/04_bp_empty.png` |
| 5 | "Filling in name and address…" | `sap_fill_form({...})` — see field table | `frames/05_bp_filled.png` |
| 6 | "Saving…" | `sap_press_key(key="Ctrl+S")` | (beat 6 references beat 7's frame) |
| 7 | "Capturing a screenshot for the documentation…" | `sap_screenshot` (shows you the picture) + `sap_run_script` `hard_copy` → `frames/07_bp_saved.png`, and copy that file as `readme-demo/BP_<Nachname>.png` | `frames/07_bp_saved.png` |
| 8 | "Now verifying it exists in SE16…" | `sap_transaction(tcode="se16")`, table `BUT000`, filter `PARTNER = <GP number>`, execute | `frames/08_se16_result.png` |
| 9 | "✓ Partner <GP number> exists in BUT000, screenshot saved as BP_<Nachname>.png." | — (report to the user) | (holds beat 8's frame) |

Beat numbering in `transcript.md` follows the table. If a step needs extra
tool calls (field discovery, popup handling), fold them into the narrative of
the current beat — do not invent new beats.

### BP form fields (labels are the keys for `sap_fill_form`)

| Key | Value |
| --- | --- |
| `Anrede` | (leave default unless user specified) |
| `Vorname` | `<first name>` |
| `Nachname` | `<last name>` |
| `Straße/Hausnummer` | `<street>` |
| `Postleitzahl/Ort` | `<postal code>` |
| `Ort` | `<city>` |
| `Land` | `DE` |

> `Postleitzahl/Ort` labels the whole address row and resolves to the postal
> code field; `Ort` addresses the city field in the same row, which has no
> separate visible label. Both keys are required.

If `sap_fill_form` reports `not_found` fields, call `sap_discover_fields` to
read the system's actual labels, adjust the keys, and retry. If the status
bar reports a duplicate or validation error after `Ctrl+S`, show the message
to the user and stop — do not create duplicates on purpose.

### Save and result evaluation

`Ctrl+S` is the save action. The `sap_press_key(key="Ctrl+S")` response
carries `status_bar_type` and `status_bar_message` — read the result directly
from that response; no separate `sap_read_status_bar` call is needed. On
`type=S` (success), extract the business partner number from the message.
Report it in beat 9 and use it as the `PARTNER` filter in beat 8. Note: run
beat 7's screenshot *after* the successful save so the status bar shows the
success message.

### Transcript sidecar format

```markdown
[beat 2] role=assistant
Logging into the dev system…
tool=sap_login

[beat 8] role=assistant frame=frames/08_se16_result.png
Now verifying it exists in SE16…
tool=sap_se16_query
```

Rules: one block per beat; `role=` is `user`, `assistant`, or `title`; `tool=`
lines only on assistant beats; `frame=` may repeat an earlier beat's file.

### After the run

Tell the user: partner number, screenshot path, SE16 confirmation, and where
the artifacts live (`readme-demo/`). If the user wants the README GIF, point
them to `scripts/README.md` (render + ffmpeg commands) — that step is
maintainer-side.

### An improved internal recipe

An improved internal skill for creating business partners may be installed in
this environment (it is not part of this repository). If present, you may
prefer it for the beat 3–6 flow; it handles more edge cases (role/grouping
prompts, company-code data). When in doubt or when fields mismatch, fall back
to the flow above — it is authoritative for this demo.
````

- [ ] **Step 2: Verify the skill file is trackable and lint-clean**

```bash
git status --porcelain --untracked-files=all | grep readme-demo/SKILL.md
uv run --locked --group spell_check codespell --ignore-words=domain-specific-terms.txt .claude/skills/readme-demo/SKILL.md
```

Expected: SKILL.md shows as untracked (proving the gitignore recipe works), codespell clean.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/readme-demo/SKILL.md
git commit -m "feat(readme-demo): demo skill with inline BP flow and beat choreography"
```

---

## Task 6: README embed

**Files:**
- Modify: `README.md` (intro, after line 11)

- [ ] **Step 1: Add the GIF + demo note**

After the intro paragraph (after the line "The MCP works with both SAP R/3 and S/4."), insert:

```markdown

![Demo: chat with Claude on the left, SAP GUI reacting on the right — login, create a business partner, screenshot, SE16 verification](docs/readme-demo.gif)

> [!TIP]
> **Try it yourself:** this demo is a skill that ships with this repository -
> clone it (or copy `.claude/skills/readme-demo/` into your project), then ask
> your agent to _run the readme demo_ (or invoke `/readme-demo` in Claude
> Code) - it logs into your system, creates a business partner, screenshots
> it, and verifies it in SE16.
```

(Task 6 as committed amended this snippet twice: prettier normalizes
`*...*` to `_..._`, and the TIP must state that the skill ships with the
repository — clone it or copy `.claude/skills/readme-demo/` — because it is
not part of the installed package and user-scope registrations never load
project-level skills. The block above reflects the committed wording.)

The GIF binary (`docs/readme-demo.gif`) needs no lint consideration — codespell
skips binaries. Note CI's Prettier workflow checks markdown only one directory
deep (`docs/*.md`, `scripts/*.md` pattern semantics of `**/*.md` under dash) —
`scripts/README.md` IS checked, so after editing it run:

```bash
npx prettier --check scripts/README.md
```

(`README.md` at the repo root is *not* covered by CI's glob, but keeping it
prettier-clean is still polite; run `npx prettier --check README.md` and fix
the new block only.)

- [ ] **Step 2: Commit the embed with a placeholder note**

The GIF binary itself comes from the real run (Task 7); this commit adds the embed so the PR diff shows placement. If `docs/readme-demo.gif` does not exist yet, keep the commit but note in the commit message that the GIF lands before merge.

```bash
git add README.md
git commit -m "docs: embed readme demo GIF and skill pointer"
```

---

## Task 7: Real run + GIF production (maintainer-side, manual, not for CI)

**Files:**
- Generated (not committed): `readme-demo/transcript.md`, `readme-demo/frames/*.png`, `readme-demo/composite/*.png`
- Create: `docs/readme-demo.gif`

This task requires the real SAP test system (VPN up, per `docs/SAP_TEST_PREREQUISITES.md`) and Claude Desktop driving the MCP. It is executed **after** the PR with Tasks 1–6 is ready, so the skill being run is the committed one.

- [ ] **Step 1: Preconditions**

- VPN up; `systems.json` points at the test system; SAP GUI scripting enabled.
- The desktop fixture warning from memory applies: the integration teardown closes **all** SAP GUI connections of the user — do not run while other SAP GUI work is open.
- The committed skill is visible to Claude Desktop (confirm project-scope discovery; if Desktop does not pick up `.claude/skills/`, import the skill file manually and note the step in SKILL.md as per spec).

- [ ] **Step 2: Run the demo**

In Claude Desktop, ask: *"run the readme demo"*. Watch that the run produces `readme-demo/transcript.md` and all six frames (`02_easy_access`, `03_bp_initial`, `04_bp_empty`, `05_bp_filled`, `07_bp_saved`, `08_se16_result`). If the run deviates (extra popups, label mismatches), fix SKILL.md and re-run — the skill is the product; do not hand-edit the transcript into shape. Before rendering, prepend the title-card block to the transcript (the skill's beats start at 1, but the spec's storyboard opens with a title card):

```markdown
[beat 0] role=title
SAP GUI MCP — chat with Claude, watch SAP do the work
```

- [ ] **Step 3: Render and encode**

```bash
uv run --locked --group tests python scripts/render_readme_demo.py --workdir readme-demo
ffmpeg -f concat -safe 0 -i readme-demo/composite/concat.txt \
  -vf "fps=10,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  readme-demo.gif
cp readme-demo.gif docs/readme-demo.gif
```

Eyeball the GIF at ~880px width: chat text legible, tool chips readable, SAP actions visible. Tune `_BEAT_SECONDS_*` in `src/sapguimcp/demo/render_readme_demo.py` if pacing feels off, re-render.

- [ ] **Step 4: Commit the GIF and push**

```bash
git add docs/readme-demo.gif src/sapguimcp/demo/render_readme_demo.py
git commit -m "docs: add readme demo GIF (staged composite of a real run)"
```

The PR description must state: *the GIF is a re-timed composite of a real run — real messages and real screenshots; only the pacing is edited.*

---

## Task 8: PR

**Files:** none (git/PR operations only)

- [ ] **Step 1: Pre-push leak check (per CLAUDE.md)**

```bash
git diff origin/main..HEAD | grep -inE "K9[0-9]{6}|/XXX/|\.hf\.de|hf\.[a-z]+\.local" || echo "clean"
```

Expected: clean. Additionally check that no committed file names the private
marketplace or recipe repo: the spec and plan must reference them only
descriptively. (Done on the feature branch: the two prose spots in the spec's
design history now use the descriptive form — "an internal skill for creating
business partners, maintained in a private internal repository" — so this
check is historical.) The committed artifacts
(SKILL.md, scripts, README) must have no such names at all:

```bash
grep -riE "hf-skills|bp-creation" src/ scripts/ README.md .claude/ || echo "clean"
```

(Only the spec/plan documents under `docs/superpowers/` are excepted from the
grep — they are internal design history, and this PR rewords them anyway.)

- [ ] **Step 2: Push and open the PR**

Branch: `feat/readme-demo` (branched from `main` before Task 1 — if executing in a worktree, this is the worktree branch). PR body: goal, honesty note (staged composite of a real run; GIF binary may land as a follow-up commit before merge), spec link, the GIF story beats, and the note that `readme-demo/` artifacts never get committed. Per repo memory rules: the PR stays blocked until a second approver (colleague) approves — do not merge on self-approval.

- [ ] **Step 3: Verify CI**

Watch the Unittests, Coverage, Linting and Formatting workflows. Offline unit tests must pass without SAP connectivity; the renderer tests are pure Pillow and must not touch the network.

---

## Acceptance criteria (from the spec)

- [ ] Skill committed at `.claude/skills/readme-demo/SKILL.md`; gitignore recipe makes it trackable; `/readme-demo/` ignored.
- [ ] Real run produces `transcript.md` + all six frames from Behavior step 2 of the spec.
- [ ] `pytest -k readme_demo` passes offline; Pillow pinned in `tests` group.
- [ ] `scripts/render_readme_demo.py` renders composites; ffmpeg command documented in `scripts/README.md`.
- [ ] README embeds the GIF with caption + "run this demo yourself" pointer.
- [ ] PR description states the honesty note.
