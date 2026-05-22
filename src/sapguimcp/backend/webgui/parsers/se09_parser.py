"""
Parser for SE09 (Transport Organizer) ARIA snapshots.

Extracts transport request data from SE09 list display.
The SE09 tree renders as flat text nodes inside a ``region "Liste"``
element. Transport entries alternate between a transport number line
and an owner+description line. Section headers provide request type,
target system, and status context.

ARIA structure (from real snapshots):
  - region "Liste":
    - text: <header>
    - text: <system info>
    - text: Workbench Workbench-Auftrag
    - text: "-> DUM Dummy Queue"
    - text: Änderbar
    - text: S4UK902153
    - text: USER01 description text
    - text: S4UK902096
    - text: USER01 another description
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SE09_MODIFIABLE_DE,
    SE09_MODIFIABLE_EN,
    SE09_RELEASED_DE,
    SE09_RELEASED_EN,
)
from sapguimcp.models.se09_models import (
    TransportListResult,
    TransportRequest,
)

logger = logging.getLogger(__name__)

__all__ = [
    "parse_se09_transport_list",
]

# =============================================================================
# Regex Patterns
# =============================================================================

# Transport number: 3-char system ID (alphanumeric) + K + 6 digits
# Optionally followed by a space and 3-digit client number (e.g., "S4UK901835 100")
_TRANSPORT_NUMBER_RE = re.compile(r"^[A-Z0-9]{3}K\d{6}(?:\s+\d{3})?$")

# Text line in ARIA snapshot: "- text: <content>" or "- text: "<content>""
_TEXT_LINE_RE = re.compile(r'^\s*- text:\s*"?(?P<content>[^"]*)"?\s*$')

# Target system line: "-> XXX ..."
_TARGET_RE = re.compile(r"^->\s+(\S+)")

# Status keywords (DE/EN) — values sourced from lang.py constants
_STATUS_KEYWORDS = {
    SE09_MODIFIABLE_DE: "Modifiable",
    SE09_MODIFIABLE_EN: "Modifiable",
    SE09_RELEASED_DE: "Released",
    SE09_RELEASED_EN: "Released",
}

# Request type keywords (DE/EN)
_REQUEST_TYPE_KEYWORDS = {
    "Workbench": "Workbench",
    "Customizing": "Customizing",
}

# Region marker
_REGION_LISTE_RE = re.compile(r'region\s+"Liste"', re.IGNORECASE)


def _extract_text_lines(snapshot: str) -> list[str]:
    """Extract all text content lines from the region 'Liste' section."""
    lines = snapshot.split("\n")
    in_region = False
    text_lines: list[str] = []

    for line in lines:
        if _REGION_LISTE_RE.search(line):
            in_region = True
            continue

        if in_region:
            # Exit region when indentation decreases significantly
            # Region content is indented deeper than "- region"
            stripped = line.lstrip()
            if stripped and not stripped.startswith("-"):
                # Non-list line, still in region
                continue
            if stripped.startswith("- cell") or stripped.startswith("- row"):
                # Exited the region into the table structure
                in_region = False
                continue

            match = _TEXT_LINE_RE.match(line)
            if match:
                content = match.group("content").strip()
                if content:
                    text_lines.append(content)

    return text_lines


def _is_transport_number(text: str) -> bool:
    """Check if text is a transport number (with optional client suffix)."""
    return bool(_TRANSPORT_NUMBER_RE.match(text.strip()))


def _extract_transport_number(text: str) -> str:
    """Extract the 10-char transport number from text, stripping any client suffix."""
    return text.strip()[:10]


def parse_se09_transport_list(
    snapshot: AriaSnapshot,
    *,
    include_objects: bool = False,  # pylint: disable=unused-argument  # reserved for future use
) -> TransportListResult:
    """
    Parse SE09 transport list from ARIA snapshot.

    The SE09 tree renders as flat text nodes inside a region "Liste".
    Transport entries alternate between a transport number line and
    an owner+description line.

    Args:
        snapshot: YAML accessibility snapshot from the SE09 list view
        include_objects: Reserved for future use (object list parsing).

    Returns:
        TransportListResult with parsed requests
    """
    now = datetime.now(UTC)

    if "Transport Organizer: Auftr" not in snapshot and "Transport Organizer: Requ" not in snapshot:
        return TransportListResult(requests=[], request_count=0, retrieved_at=now)

    text_lines = _extract_text_lines(snapshot)
    if not text_lines:
        return TransportListResult(requests=[], request_count=0, retrieved_at=now)

    requests = _parse_transport_entries(text_lines)

    return TransportListResult(
        requests=requests,
        request_count=len(requests),
        retrieved_at=now,
    )


def _parse_transport_entries(text_lines: list[str]) -> list[TransportRequest]:
    """Parse transport entries from extracted text lines."""
    current_request_type = ""
    current_target = ""
    current_status = ""
    requests: list[TransportRequest] = []

    i = 0
    while i < len(text_lines):
        line = text_lines[i]

        if line in _STATUS_KEYWORDS:
            current_status = _STATUS_KEYWORDS[line]
            i += 1
            continue

        for keyword, type_name in _REQUEST_TYPE_KEYWORDS.items():
            if keyword in line and ("Auftrag" in line or "Aufträge" in line or "Request" in line):
                current_request_type = type_name
                break

        target_match = _TARGET_RE.match(line)
        if target_match:
            current_target = target_match.group(1)
            i += 1
            continue

        if _is_transport_number(line):
            transport_number = _extract_transport_number(line)
            owner, description = "", ""
            if i + 1 < len(text_lines):
                next_line = text_lines[i + 1]
                if not _is_transport_number(next_line) and next_line not in _STATUS_KEYWORDS:
                    parts = next_line.split(None, 1)
                    if parts:
                        owner = parts[0]
                        description = parts[1] if len(parts) > 1 else ""
                    i += 1

            requests.append(
                TransportRequest(
                    request_number=transport_number,
                    description=description,
                    owner=owner,
                    status=current_status,
                    request_type=current_request_type,
                    target_system=current_target,
                )
            )
            i += 1
            continue

        i += 1

    return requests
