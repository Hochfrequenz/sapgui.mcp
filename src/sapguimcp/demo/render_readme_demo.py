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
