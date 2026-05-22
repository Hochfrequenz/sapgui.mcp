"""
Parser for SM37 (Job Overview) ARIA snapshots.

Extracts background job list and job log data from SM37 display screens.
Handles both German and English SAP installations.

SM37 job list uses a flat text-based list inside a region, NOT an ALV grid.
Each job row appears as:
    - checkbox
    - text: JOBNAME USER STATUS [DATE TIME] DELAY DURATION MANDANT

Column headers appear as buttons: "Jobname", "Status", "Startdatum", etc.
"""

import logging
import re

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import SM37_STATUS_MAP_DE, SM37_STATUS_MAP_EN
from sapguimcp.models.sm37_models import SM37Job, SM37JobLog

logger = logging.getLogger(__name__)

__all__ = [
    "parse_sm37_job_list",
    "parse_sm37_job_log",
    "is_no_jobs_found",
    "is_job_list_screen",
]


# =============================================================================
# Detection helpers
# =============================================================================

_NO_JOBS_PATTERNS = [
    "kein job entspricht den selektionsbedingungen",
    "no job matches the selection criteria",
    "keine jobs gefunden",
    "no jobs found",
]

# Job list heading
_JOB_LIST_HEADING_DE = "Jobübersicht"
_JOB_LIST_HEADING_EN = "Job Overview"


def is_no_jobs_found(snapshot: AriaSnapshot) -> bool:
    """Check if the snapshot indicates no jobs were found."""
    snapshot_lower = snapshot.lower()
    return any(pattern in snapshot_lower for pattern in _NO_JOBS_PATTERNS)


def is_job_list_screen(snapshot: AriaSnapshot) -> bool:
    """Check if we're on the job list results screen (not the selection screen)."""
    return _JOB_LIST_HEADING_DE in snapshot or _JOB_LIST_HEADING_EN in snapshot


# =============================================================================
# Job row parsing
# =============================================================================

# All known DE + EN status values (lowercase for matching)
_ALL_STATUS_KEYS = set(SM37_STATUS_MAP_DE.keys()) | set(SM37_STATUS_MAP_EN.keys())

# Pattern to match job data rows in the text list.
# Rows appear after checkbox as: text: JOBNAME USER STATUS [DATE TIME] DELAY DURATION MANDANT
# For released/scheduled (no date): "JOBNAME USER freigegeben 0 0 210"
# For finished (with date): "JOBNAME USER fertig 22.02.2026 00:00:06 0 6 210"
_JOB_TEXT_PATTERN = re.compile(
    r"- text:\s+(.+)",
    re.MULTILINE,
)


def _normalize_status(status_text: str) -> str:
    """Normalize a DE/EN status text to canonical English form."""
    status_lower = status_text.strip().lower()

    if status_lower in SM37_STATUS_MAP_DE:
        return SM37_STATUS_MAP_DE[status_lower]

    if status_lower in SM37_STATUS_MAP_EN:
        return SM37_STATUS_MAP_EN[status_lower]

    return status_text.strip()


def _parse_job_row(text: str) -> SM37Job | None:
    """
    Parse a single job row text line into an SM37Job.

    Formats observed:
    - Without date: "JOBNAME USER STATUS DELAY DURATION MANDANT"
    - With date: "JOBNAME USER STATUS DD.MM.YYYY HH:MM:SS DELAY DURATION MANDANT"

    Returns None if the text doesn't match a job row pattern.
    """
    parts = text.strip().split()
    if len(parts) < 4:
        return None

    # Find the status token - it should be the 3rd token (index 2)
    # but job names can contain spaces, so scan for a known status
    status_idx = None
    for i, part in enumerate(parts):
        if part.lower() in _ALL_STATUS_KEYS:
            status_idx = i
            break

    if status_idx is None or status_idx < 2:
        return None

    job_name = " ".join(parts[: status_idx - 1])
    user = parts[status_idx - 1]
    status_raw = parts[status_idx]
    remaining = parts[status_idx + 1 :]

    # Check if next token is a date (DD.MM.YYYY or MM/DD/YYYY)
    start_time = None
    date_pattern = re.compile(r"\d{2}[./]\d{2}[./]\d{4}")

    if remaining and date_pattern.match(remaining[0]):
        date_str = remaining[0]
        time_str = remaining[1] if len(remaining) > 1 else ""
        start_time = f"{date_str} {time_str}".strip()
        remaining = remaining[2:]

    # Remaining: DELAY DURATION MANDANT (integers)
    duration = None
    mandant = ""
    if len(remaining) >= 3:
        duration = remaining[1] if remaining[1] != "0" else None
        mandant = remaining[2]
    elif len(remaining) >= 2:
        duration = remaining[0] if remaining[0] != "0" else None
        mandant = remaining[1]

    return SM37Job(
        job_name=job_name,
        status=_normalize_status(status_raw),
        start_time=start_time,
        duration=f"{duration}s" if duration else None,
        user=user,
        mandant=mandant,
    )


def parse_sm37_job_list(snapshot: AriaSnapshot) -> list[SM37Job]:
    """
    Parse the SM37 job list from an ARIA snapshot.

    The job list is a flat text-based list where each job appears as:
        - checkbox
        - text: JOBNAME USER STATUS [DATE TIME] DELAY DURATION MANDANT

    Duplicate rows are deduplicated (SM37 sometimes renders each row twice).

    Args:
        snapshot: YAML accessibility snapshot of the SM37 job list screen

    Returns:
        List of SM37Job objects. Empty list if no jobs found.
    """
    if is_no_jobs_found(snapshot):
        return []

    if not is_job_list_screen(snapshot):
        return []

    jobs: list[SM37Job] = []
    seen: set[tuple[str, str, str, str | None, str]] = set()

    for match in _JOB_TEXT_PATTERN.finditer(snapshot):
        text = match.group(1).strip()

        # Skip non-job text lines
        if text.startswith('"') or text.startswith("geplant") or text.startswith("scheduled"):
            continue
        if "Selektierte" in text or "Selected" in text:
            continue
        if "eventgesteuert" in text or "event-driven" in text:
            continue
        if "ABAP Programm" in text or "ABAP Program" in text:
            continue

        job = _parse_job_row(text)
        if job is None:
            continue

        # Deduplicate (include mandant so jobs across clients aren't collapsed)
        key = (job.job_name, job.user, job.status, job.start_time, job.mandant)
        if key in seen:
            continue
        seen.add(key)

        jobs.append(job)

    return jobs


# =============================================================================
# Job log parsing
# =============================================================================


def parse_sm37_job_log(snapshot: AriaSnapshot, job_name: str) -> SM37JobLog:
    """
    Parse the SM37 job log from an ARIA snapshot.

    Args:
        snapshot: YAML accessibility snapshot of the SM37 job log screen
        job_name: Name of the job (for the result object)

    Returns:
        SM37JobLog with extracted log lines.
    """
    log_lines: list[str] = []

    for match in _JOB_TEXT_PATTERN.finditer(snapshot):
        line = match.group(1).strip()
        if line and len(line) > 2:
            # Skip navigation hints and UI chrome
            if line.startswith('"'):
                line = line.strip('"')
            if "Zum Auswählen" in line or "To select" in line:
                continue
            if "Selektierte" in line or "Selected" in line:
                continue
            log_lines.append(line)

    return SM37JobLog(
        job_name=job_name,
        log_lines=log_lines,
    )
