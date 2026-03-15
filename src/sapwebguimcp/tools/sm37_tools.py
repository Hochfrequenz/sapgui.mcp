"""
SM37 (Job Overview) lookup tool.

Provides a read-only tool to list background jobs from SM37
with status/date/user filters, and optionally retrieve job logs.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.backend.webgui.parsers.sm37_parser import (
    is_no_jobs_found,
    parse_sm37_job_list,
    parse_sm37_job_log,
)
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.models.sm37_models import SM37Job, SM37JobListResult, SM37JobLog
from sapwebguimcp.tools._backend_utils import _is_desktop_backend
from sapwebguimcp.tools.screen_state_helpers import bilingual_target, ensure_screen_state
from sapwebguimcp.utils import SapLanguage, format_sap_date

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

__all__ = ["register_sm37_tools"]

_MAX_JOBS = 200

_ALL_STATUSES = ["scheduled", "released", "ready", "active", "finished", "canceled"]


async def _fill_selection_screen(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-locals
    backend: "SapUiBackend",
    job_name: str,
    username: str | None,
    statuses: list[str] | None,
    from_date: str | None,
    to_date: str | None,
    language: SapLanguage,
) -> list[str]:
    """Fill the SM37 selection screen fields."""
    errors: list[str] = []

    # Build target for checkboxes + text fields in one declarative call
    effective_statuses = set(statuses) if statuses else set(_ALL_STATUSES)
    fields_de: dict[str, str] = {"Jobname": job_name}
    fields_en: dict[str, str] = {"Job name": job_name}
    if username is not None:
        fields_de["Benutzername"] = username
        fields_en["User name"] = username

    target = bilingual_target(
        checkboxes_de={
            "Geplant": "scheduled" in effective_statuses,
            "Freigegeben": "released" in effective_statuses,
            "Bereit": "ready" in effective_statuses,
            "Aktiv": "active" in effective_statuses,
            "Fertig": "finished" in effective_statuses,
            "Abgebrochen": "canceled" in effective_statuses,
        },
        checkboxes_en={
            "Scheduled": "scheduled" in effective_statuses,
            "Released": "released" in effective_statuses,
            "Ready": "ready" in effective_statuses,
            "Active": "active" in effective_statuses,
            "Finished": "finished" in effective_statuses,
            "Canceled": "canceled" in effective_statuses,
        },
        fields_de=fields_de,
        fields_en=fields_en,
    )
    state_result = await ensure_screen_state(backend, target)
    if not state_result.success:
        errors.append(f"Failed to set selection screen state: {state_result.error}")
    errors.extend(state_result.warnings)

    # Date fields are filled manually (not via ensure_screen_state) because they
    # require format_sap_date() which depends on the configured language setting.
    # The ARIA snapshot values use SAP's display format which may differ from the
    # input format, making snapshot-based verification unreliable for dates.
    if from_date or to_date:
        if from_date:
            sap_from = format_sap_date(from_date, language)
            for label in ["von Datum", "From Date"]:
                try:
                    await backend.fill_field(label, sap_from)
                    break
                except ValueError:
                    continue
            else:
                errors.append("Could not set from_date: field not found")

        if to_date:
            sap_to = format_sap_date(to_date, language)
            for label in ["bis Datum", "To Date"]:
                try:
                    await backend.fill_field(label, sap_to)
                    break
                except ValueError:
                    continue
            else:
                errors.append("Could not set to_date: field not found")

    return errors


_JOB_LOG_HEADING_DE = "Job Log Einträge"
_JOB_LOG_HEADING_EN = "Job Log Entries"


def _is_job_log_screen(snapshot: str) -> bool:
    """Check if the snapshot shows a job log screen (not the job list)."""
    return _JOB_LOG_HEADING_DE in snapshot or _JOB_LOG_HEADING_EN in snapshot


async def _fetch_job_log(backend: "SapUiBackend", language: SapLanguage) -> SM37JobLog | None:
    """
    Select the first job row and fetch its job log.

    Clicks the Job-Log button, validates the screen changed, then parses the log.
    """
    try:
        # Select the first job row before clicking Job-Log
        await backend.click_table_cell(1, 0, "click")
        await backend.wait_for_ready()

        # Click the Job-Log button
        log_button_text = "Job-Log" if language == "DE" else "Job Log"
        try:
            await backend.click_button(log_button_text)
        except ValueError:
            logger.warning("Job log button not found label=%r", log_button_text)
            return None

        await backend.wait_for_ready()

        snapshot = AriaSnapshot(await backend.get_snapshot())

        if not _is_job_log_screen(str(snapshot)):
            logger.warning("Expected job log screen but got something else, skipping log parse")
            await backend.press_key("F3")
            await backend.wait_for_ready()
            return None

        job_log = parse_sm37_job_log(snapshot, "")

        # Navigate back (F3)
        await backend.press_key("F3")
        await backend.wait_for_ready()

        return job_log

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Fetching job log error=%s", e)
        return None


async def _execute_sm37_lookup_desktop(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
    backend: "SapUiBackend",
    job_name: str,
    username: str | None,
    statuses: list[str] | None,
    from_date: str | None,
    to_date: str | None,
) -> SM37JobListResult:
    """Desktop-specific SM37 lookup using read_table instead of ARIA parsing."""
    from sapwebguimcp.models import TableData  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    settings = get_settings()
    language: SapLanguage = settings.sap_language

    logger.info("SM37 desktop backend path", extra={"job_name": job_name})

    tx_result = await backend.enter_transaction("SM37")
    if not tx_result.success:
        return SM37JobListResult.failure(
            error=f"Failed to navigate to SM37: {tx_result.error}",
            jobs=[],
            job_count=0,
            filters_applied={},
            retrieved_at=now,
        )
    await backend.wait_for_ready()

    # Fill selection screen fields via focus_and_type
    for label in ["Jobname", "Job name", "Job Name"]:
        try:
            if await backend.focus_and_type(label, job_name, delay_ms=50):
                break
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    if username is not None:
        for label in ["Benutzername", "User name", "User Name"]:
            try:
                if await backend.focus_and_type(label, username, delay_ms=50):
                    break
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    # Date fields
    if from_date:
        sap_from = format_sap_date(from_date, language)
        for label in ["von Datum", "From Date"]:
            try:
                await backend.fill_field(label, sap_from)
                break
            except ValueError:
                continue

    if to_date:
        sap_to = format_sap_date(to_date, language)
        for label in ["bis Datum", "To Date"]:
            try:
                await backend.fill_field(label, sap_to)
                break
            except ValueError:
                continue

    # Execute (F8)
    await backend.press_key("F8")
    await backend.wait_for_ready()

    # Check status bar for errors / no results
    sbar = await backend.get_status_bar()
    filters_applied: dict[str, str] = {"job_name": job_name}
    if username:
        filters_applied["username"] = username
    if statuses:
        filters_applied["status"] = ",".join(statuses)
    if from_date:
        filters_applied["from_date"] = from_date
    if to_date:
        filters_applied["to_date"] = to_date

    if sbar.type == "E":
        return SM37JobListResult.failure(
            error=f"SM37 error: {sbar.message}",
            jobs=[],
            job_count=0,
            filters_applied=filters_applied,
            retrieved_at=now,
        )

    if sbar.message and any(
        msg in sbar.message.lower() for msg in ["no jobs found", "keine jobs", "keine hintergrundjobs"]
    ):
        return SM37JobListResult(
            jobs=[],
            job_count=0,
            filters_applied=filters_applied,
            retrieved_at=now,
        )

    # Read table data
    table_data: TableData = await backend.read_table(start_row=1, max_rows=_MAX_JOBS)

    if not table_data.headers:
        return SM37JobListResult.failure(
            error="Could not read SM37 job list table",
            jobs=[],
            job_count=0,
            filters_applied=filters_applied,
            retrieved_at=now,
        )

    # Convert table rows to SM37Job models
    # SM37 ALV grid columns vary by language but typically include:
    # Jobname/Job Name, Status, Startdatum/Start Date, Startzeit/Start Time, Dauer/Duration, Ersteller/Created By
    jobs: list[SM37Job] = []
    for tr in table_data.rows:
        d = tr.data
        # Try common column name variants
        jn = d.get("Jobname", d.get("Job Name", d.get("Job name", "")))
        st = d.get("Status", "")
        sd = d.get("Startdatum", d.get("Start Date", d.get("Start date", "")))
        sz = d.get("Startzeit", d.get("Start Time", d.get("Start time", "")))
        start_time = f"{sd} {sz}".strip() if sd or sz else None
        dur = d.get("Dauer", d.get("Duration", d.get("Dauer(s)", None)))
        user = d.get("Ersteller", d.get("Created By", d.get("Created by", "")))
        mandant = d.get("Mandant", d.get("Client", ""))

        jobs.append(
            SM37Job(
                job_name=jn,
                status=st,
                start_time=start_time,
                duration=dur,
                user=user,
                mandant=mandant,
            )
        )

    if len(jobs) > _MAX_JOBS:
        jobs = jobs[:_MAX_JOBS]

    return SM37JobListResult(
        jobs=jobs,
        job_count=len(jobs),
        filters_applied=filters_applied,
        retrieved_at=now,
    )


async def _execute_sm37_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    backend: "SapUiBackend",
    job_name: str,
    username: str | None,
    statuses: list[str] | None,
    from_date: str | None,
    to_date: str | None,
    include_log: bool,
) -> SM37JobListResult:
    """Execute the SM37 lookup workflow on the given backend."""
    now = datetime.now(UTC)
    settings = get_settings()
    language: SapLanguage = settings.sap_language

    # Desktop backend: use read_table instead of ARIA snapshot parsing
    if _is_desktop_backend(backend):
        return await _execute_sm37_lookup_desktop(backend, job_name, username, statuses, from_date, to_date)

    tx_result = await backend.enter_transaction("SM37")
    if not tx_result.success:
        return SM37JobListResult.failure(
            error=f"Failed to navigate to SM37: {tx_result.error}",
            jobs=[],
            job_count=0,
            filters_applied={},
            retrieved_at=now,
        )

    await backend.wait_for_ready()

    fill_errors = await _fill_selection_screen(backend, job_name, username, statuses, from_date, to_date, language)
    if fill_errors:
        logger.warning("Selection field errors errors=%r", fill_errors)

    filters_applied: dict[str, str] = {"job_name": job_name}
    if username:
        filters_applied["username"] = username
    if statuses:
        filters_applied["status"] = ",".join(statuses)
    if from_date:
        filters_applied["from_date"] = from_date
    if to_date:
        filters_applied["to_date"] = to_date

    # Execute (F8)
    await backend.press_key("F8")
    await backend.wait_for_ready()

    snapshot = AriaSnapshot(await backend.get_snapshot())

    if is_no_jobs_found(snapshot):
        return SM37JobListResult(
            jobs=[],
            job_count=0,
            filters_applied=filters_applied,
            retrieved_at=now,
        )

    jobs = parse_sm37_job_list(snapshot)

    if len(jobs) > _MAX_JOBS:
        logger.warning("Truncating job list total=%d max=%d", len(jobs), _MAX_JOBS)
        jobs = jobs[:_MAX_JOBS]

    # Fetch job log if requested and exactly one job
    job_log: SM37JobLog | None = None
    if include_log and len(jobs) == 1:
        job_log = await _fetch_job_log(backend, language)
        if job_log:
            job_log.job_name = jobs[0].job_name

    return SM37JobListResult(
        jobs=jobs,
        job_count=len(jobs),
        filters_applied=filters_applied,
        job_log=job_log,
        retrieved_at=now,
    )


def register_sm37_tools(mcp: FastMCP) -> None:
    """Register SM37 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "List background jobs from SM37 (Job Overview). "
            "USE THIS instead of sap_transaction('SM37') - faster and returns structured data.\n\n"
            "Filters: job name (wildcards like *BILLING*), username, status "
            "(scheduled/released/ready/active/finished/canceled), date range.\n\n"
            "Note: status=None keeps SAP defaults (all checked except 'Scheduled'). "
            "Pass status=['scheduled'] explicitly to include only scheduled jobs.\n\n"
            "When include_log=True and exactly one job matches, the job log is included.\n\n"
            "Returns job list with name, status, start time, duration, user, and SAP client (mandant)."
        ),
    )
    async def sap_sm37_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        job_name: str = "*",
        username: str | None = "*",
        status: (
            list[
                Literal[
                    "scheduled",
                    "released",
                    "ready",
                    "active",
                    "finished",
                    "canceled",
                ]
            ]
            | None
        ) = None,
        from_date: str | None = None,
        to_date: str | None = None,
        include_log: bool = False,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SM37JobListResult:
        """
        List background jobs from SM37.

        Args:
            job_name: Job name filter (supports * wildcard, default: *)
            username: User filter (default: * for all users, None to keep SAP default)
            status: Status filter list (default: None = all statuses).
            from_date: Start date filter in ISO format (YYYY-MM-DD)
            to_date: End date filter in ISO format (YYYY-MM-DD)
            include_log: Fetch job log when exactly one job matches (default: False)
            output_file: If provided, write full results to this JSON file
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_sm37_lookup")
        except ValueError as e:
            return SM37JobListResult.failure(
                error=f"Session error: {e}",
                jobs=[],
                job_count=0,
                filters_applied={},
                retrieved_at=datetime.now(UTC),
            )

        result = await _execute_sm37_lookup(
            backend=backend,
            job_name=job_name,
            username=username,
            statuses=list(status) if status else None,
            from_date=from_date,
            to_date=to_date,
            include_log=include_log,
        )

        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
            logger.info("Wrote SM37 results path=%s", str(output_path))

        return result
