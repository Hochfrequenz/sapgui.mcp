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
    - text: KLEINK description text
    - text: S4UK902096
    - text: KLEINK another description
"""

import logging
import re
from datetime import UTC, datetime

from sapwebguimcp.models.se09_models import (
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
_TRANSPORT_NUMBER_RE = re.compile(r"^[A-Z0-9]{3}K\d{6}$")

# Text line in ARIA snapshot: "- text: <content>" or "- text: "<content>""
_TEXT_LINE_RE = re.compile(r'^\s*- text:\s*"?(?P<content>[^"]*)"?\s*$')

# Target system line: "-> XXX ..."
_TARGET_RE = re.compile(r"^->\s+(\S+)")

# Status keywords (DE/EN)
_STATUS_KEYWORDS = {
    "Änderbar": "Modifiable",
    "Modifiable": "Modifiable",
    "Freigegeben": "Released",
    "Released": "Released",
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
    """Check if text is a transport number."""
    return bool(_TRANSPORT_NUMBER_RE.match(text.strip()))


def parse_se09_transport_list(
    snapshot: str,
    include_objects: bool = False,
) -> TransportListResult:
    """
    Parse SE09 transport list from ARIA snapshot.

    The SE09 tree renders as flat text nodes inside a region "Liste".
    Transport entries alternate between a transport number line and
    an owner+description line.

    Args:
        snapshot: YAML accessibility snapshot from the SE09 list view
        include_objects: Not supported in v1 (tree doesn't expose objects in ARIA)

    Returns:
        TransportListResult with parsed requests
    """
    now = datetime.now(UTC)

    # Check for results page heading
    if "Transport Organizer: Auftr" not in snapshot and "Transport Organizer: Requ" not in snapshot:
        # Still on initial screen or different page
        return TransportListResult(
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    text_lines = _extract_text_lines(snapshot)
    if not text_lines:
        return TransportListResult(
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    # Parse section headers and transport entries
    current_request_type = ""
    current_target = ""
    current_status = ""
    requests: list[TransportRequest] = []

    i = 0
    while i < len(text_lines):
        line = text_lines[i]

        # Check for status keyword
        if line in _STATUS_KEYWORDS:
            current_status = _STATUS_KEYWORDS[line]
            i += 1
            continue

        # Check for request type keyword
        for keyword, type_name in _REQUEST_TYPE_KEYWORDS.items():
            if keyword in line and ("Auftrag" in line or "Request" in line):
                current_request_type = type_name
                break

        # Check for target system
        target_match = _TARGET_RE.match(line)
        if target_match:
            current_target = target_match.group(1)
            i += 1
            continue

        # Check for transport number
        if _is_transport_number(line):
            transport_num = line.strip()
            owner = ""
            description = ""

            # Next line should be "OWNER description text"
            if i + 1 < len(text_lines):
                next_line = text_lines[i + 1]
                if not _is_transport_number(next_line) and next_line not in _STATUS_KEYWORDS:
                    parts = next_line.split(None, 1)
                    if parts:
                        owner = parts[0]
                        description = parts[1] if len(parts) > 1 else ""
                    i += 1  # Skip the owner/description line

            requests.append(
                TransportRequest(
                    request_number=transport_num,
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

    return TransportListResult(
        requests=requests,
        request_count=len(requests),
        retrieved_at=now,
    )
