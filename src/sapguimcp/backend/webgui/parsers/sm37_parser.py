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
from sapguimcp.lang import LanguagePack
from sapguimcp.lang.schema import JobStatus
from sapguimcp.models.sm37_models import SM37Job, SM37JobLog

logger = logging.getLogger(__name__)

__all__ = [
    "parse_sm37_job_list",
    "parse_sm37_job_log",
    "is_no_jobs_found",
    "is_job_list_screen",
    "normalize_job_status",
]


# =============================================================================
# Detection helpers
# =============================================================================


def is_no_jobs_found(snapshot: AriaSnapshot, t: LanguagePack) -> bool:
    """Check if the snapshot indicates no jobs were found."""
    return t.sm37.no_jobs.contains(snapshot)


def is_job_list_screen(snapshot: AriaSnapshot, t: LanguagePack) -> bool:
    """Check if we're on the job list results screen (not the selection screen)."""
    return t.sm37.job_list_heading.contains(snapshot)


# =============================================================================
# Job row parsing
# =============================================================================


def _status_tokens(t: LanguagePack) -> set[str]:
    """Every status text of the session's view (lowercase), the tokens that mark the status column of a row."""
    return {variant.lower() for text in t.sm37.status.values() for variant in text}


# Pattern to match job data rows in the text list.
# Rows appear after checkbox as: text: JOBNAME USER STATUS [DATE TIME] DELAY DURATION MANDANT
# For released/scheduled (no date): "JOBNAME USER freigegeben 0 0 210"
# For finished (with date): "JOBNAME USER fertig 22.02.2026 00:00:06 0 6 210"
_JOB_TEXT_PATTERN = re.compile(
    r"- text:\s+(.+)",
    re.MULTILINE,
)


def normalize_job_status(status_text: str, t: LanguagePack) -> str:
    """Normalize a status text of the session's language to the canonical ``JobStatus`` value.

    Texts of no known status are returned trimmed. Shared by the WebGUI parser and the desktop tool.
    """
    stripped = status_text.strip()
    for status, text in t.sm37.status.items():
        if text.equals(stripped):
            return status.value
    return stripped


def _parse_job_row(text: str, t: LanguagePack) -> SM37Job | None:
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
    status_tokens = _status_tokens(t)
    for i, part in enumerate(parts):
        if part.lower() in status_tokens:
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
        status=normalize_job_status(status_raw, t),
        start_time=start_time,
        duration=f"{duration}s" if duration else None,
        user=user,
        mandant=mandant,
    )


def parse_sm37_job_list(snapshot: AriaSnapshot, t: LanguagePack) -> list[SM37Job]:
    """
    Parse the SM37 job list from an ARIA snapshot.

    The job list is a flat text-based list where each job appears as:
        - checkbox
        - text: JOBNAME USER STATUS [DATE TIME] DELAY DURATION MANDANT

    Duplicate rows are deduplicated (SM37 sometimes renders each row twice).

    Args:
        snapshot: YAML accessibility snapshot of the SM37 job list screen
        t: Language pack of the session

    Returns:
        List of SM37Job objects. Empty list if no jobs found.
    """
    if is_no_jobs_found(snapshot, t):
        return []

    if not is_job_list_screen(snapshot, t):
        return []

    # the list shows the status in lower case; "Sched." is only the checkbox text
    scheduled = tuple(v.lower() for v in t.sm37.status[JobStatus.SCHEDULED] if not v.endswith("."))

    jobs: list[SM37Job] = []
    seen: set[tuple[str, str, str, str | None, str]] = set()

    for match in _JOB_TEXT_PATTERN.finditer(snapshot):
        text = match.group(1).strip()

        # Skip non-job text lines
        if text.startswith('"') or text.startswith(scheduled):
            continue
        if t.sm37.selected_hint.contains(text):
            continue
        if t.sm37.event_driven.contains(text):
            continue
        if t.sm37.abap_program.contains(text):
            continue

        job = _parse_job_row(text, t)
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


def parse_sm37_job_log(snapshot: AriaSnapshot, job_name: str, t: LanguagePack) -> SM37JobLog:
    """
    Parse the SM37 job log from an ARIA snapshot.

    Args:
        snapshot: YAML accessibility snapshot of the SM37 job log screen
        job_name: Name of the job (for the result object)
        t: Language pack of the session

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
            if t.sm37.select_hint.contains(line):
                continue
            if t.sm37.selected_hint.contains(line):
                continue
            log_lines.append(line)

    return SM37JobLog(
        job_name=job_name,
        log_lines=log_lines,
    )
