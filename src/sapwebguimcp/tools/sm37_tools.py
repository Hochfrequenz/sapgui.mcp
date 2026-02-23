"""
SM37 (Job Overview) lookup tool.

Provides a read-only tool to list background jobs from SM37
with status/date/user filters, and optionally retrieve job logs.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import Locator, Page

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.models.sm37_models import SM37JobListResult, SM37JobLog
from sapwebguimcp.parsers.sm37_parser import is_no_jobs_found, parse_sm37_job_list, parse_sm37_job_log
from sapwebguimcp.tools.sap_tool_impl import _load_js, _load_js_with_field_utils
from sapwebguimcp.utils import SapLanguage, format_sap_date

logger = logging.getLogger(__name__)

__all__ = ["register_sm37_tools"]

_MAX_JOBS = 200

# Checkbox label mapping: canonical name -> (DE label, EN label)
# Labels match the ARIA checkbox names on the SM37 selection screen.
_STATUS_CHECKBOX_MAP: dict[str, tuple[str, str]] = {
    "scheduled": ("Geplant", "Scheduled"),
    "released": ("Freigegeben", "Released"),
    "ready": ("Bereit", "Ready"),
    "active": ("Aktiv", "Active"),
    "finished": ("Fertig", "Finished"),
    "canceled": ("Abgebrochen", "Canceled"),
}

_ALL_STATUSES = list(_STATUS_CHECKBOX_MAP.keys())


async def _fill_form_on_page(page: Page, fields: dict[str, str]) -> list[str]:
    """Fill form fields on a specific page. Returns list of field names not found."""
    result = await page.evaluate(
        _load_js_with_field_utils("fill_form_fields.js"),
        {"fields": fields},
    )
    not_found: list[str] = result.get("notFound", [])
    return not_found


async def _navigate_transaction(page: Page, tcode: str) -> str | None:
    """Navigate to a transaction on a specific page. Returns error string or None on success."""
    okcode = await page.query_selector("#ToolbarOkCode")
    if not okcode or not await okcode.is_visible():
        for selector in ["input[id*='OkCode']", "input[lsdata*='OKCODE']"]:
            okcode = await page.query_selector(selector)
            if okcode and await okcode.is_visible():
                break
        else:
            return f"OK-Code field not found for transaction {tcode}"

    await page.bring_to_front()
    await page.wait_for_timeout(500)
    await okcode.click()
    await page.wait_for_timeout(200)
    await page.evaluate(_load_js("set_okcode_field.js"), {"transactionInput": f"/n{tcode}"})
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=15000)
    return None


async def _set_status_checkboxes(page: Page, statuses: list[str], language: str) -> list[str]:
    """
    Set status checkboxes on the SM37 selection screen.

    If statuses contains all statuses, leave unchanged.
    Otherwise, uncheck all and check only requested.
    """
    if not statuses or set(statuses) == set(_ALL_STATUSES):
        return []

    errors: list[str] = []

    for status_name in _ALL_STATUSES:
        de_label, en_label = _STATUS_CHECKBOX_MAP[status_name]
        label = de_label if language.upper() == "DE" else en_label
        should_be_checked = status_name in statuses

        try:
            checkbox = page.get_by_role("checkbox", name=re.compile(re.escape(label), re.IGNORECASE))

            if await checkbox.count() == 0:
                errors.append(f"Checkbox '{label}' not found")
                continue

            is_checked = await checkbox.is_checked()

            if should_be_checked and not is_checked:
                await checkbox.check()
                await page.wait_for_timeout(100)
            elif not should_be_checked and is_checked:
                await checkbox.uncheck()
                await page.wait_for_timeout(100)

        except Exception as e:  # pylint: disable=broad-exception-caught
            errors.append(f"Failed to set checkbox '{label}': {e}")
            logger.warning("Checkbox error label=%r error=%s", label, e)

    return errors


async def _fill_date_field(
    page: Page, date_images: Locator, img_index: int, fallback_index: int, sap_date: str
) -> str | None:
    """Fill a single date field anchored to a 'Datum'/'Date' image, with positional fallback."""
    try:
        if await date_images.count() > img_index:
            box = date_images.nth(img_index).locator("xpath=following-sibling::input[1]")
            if await box.count() > 0:
                await box.fill(sap_date)
                return None
        # Fallback: positional index
        all_boxes = page.locator("input[type='text']")
        if await all_boxes.count() > fallback_index:
            await all_boxes.nth(fallback_index).fill(sap_date)
            return None
        return "Could not find date field anchor (img 'Datum'/'Date')"
    except Exception as e:  # pylint: disable=broad-exception-caught
        return str(e)


async def _fill_selection_screen(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches
    page: Page,
    job_name: str,
    username: str | None,
    statuses: list[str] | None,
    from_date: str | None,
    to_date: str | None,
    language: SapLanguage,
) -> list[str]:
    """Fill the SM37 selection screen fields."""
    errors: list[str] = []

    # Fill job name - try DE then EN label
    for labels in [{"Jobname": job_name}, {"Job name": job_name}]:
        not_found = await _fill_form_on_page(page, labels)
        if not not_found:
            break
    else:
        errors.append("Could not find job name field")

    # Fill username
    if username is not None:
        for labels in [{"Benutzername": username}, {"User name": username}]:
            not_found = await _fill_form_on_page(page, labels)
            if not not_found:
                break
        else:
            errors.append("Could not find username field")

    # Set status checkboxes
    if statuses:
        checkbox_errors = await _set_status_checkboxes(page, statuses, language)
        errors.extend(checkbox_errors)

    # Date fields: anchor to img "Datum"/"Date", fallback to positional index
    if from_date or to_date:
        date_img_label = "Datum" if language.upper() == "DE" else "Date"
        date_images = page.get_by_role("img", name=date_img_label)

        if from_date:
            err = await _fill_date_field(page, date_images, 0, 2, format_sap_date(from_date, language))
            if err:
                errors.append(f"Could not set from_date: {err}")

        if to_date:
            err = await _fill_date_field(page, date_images, 1, 3, format_sap_date(to_date, language))
            if err:
                errors.append(f"Could not set to_date: {err}")

    return errors


async def _fetch_job_log(page: Page, language: SapLanguage) -> SM37JobLog | None:
    """
    Fetch the job log for the currently selected job.

    The job must already be selected in the job list.
    """
    try:
        log_button_text = "Job-Log" if language == "DE" else "Job Log"
        button = page.get_by_role("button", name=re.compile(re.escape(log_button_text), re.IGNORECASE))

        if await button.count() == 0:
            logger.warning("Job log button not found label=%r", log_button_text)
            return None

        await button.click()
        await page.wait_for_timeout(2000)
        await page.wait_for_load_state("networkidle")

        snapshot = await page.locator("body").aria_snapshot()
        job_log = parse_sm37_job_log(snapshot, "")

        # Navigate back (F3)
        await page.keyboard.press("F3")
        await page.wait_for_timeout(1000)

        return job_log

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Fetching job log error=%s", e)
        return None


async def _execute_sm37_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    page: Page,
    job_name: str,
    username: str | None,
    statuses: list[str] | None,
    from_date: str | None,
    to_date: str | None,
    include_log: bool,
) -> SM37JobListResult:
    """Execute the SM37 lookup workflow on the given page."""
    now = datetime.now(UTC)
    settings = get_settings()
    language: SapLanguage = settings.sap_language

    tx_error = await _navigate_transaction(page, "SM37")
    if tx_error:
        return SM37JobListResult.failure(
            error=f"Failed to navigate to SM37: {tx_error}",
            jobs=[],
            job_count=0,
            filters_applied={},
            retrieved_at=now,
        )

    await page.wait_for_timeout(1000)

    fill_errors = await _fill_selection_screen(page, job_name, username, statuses, from_date, to_date, language)
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
    await page.keyboard.press("F8")
    await page.wait_for_timeout(3000)
    await page.wait_for_load_state("networkidle")

    snapshot = await page.locator("body").aria_snapshot()

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
        job_log = await _fetch_job_log(page, language)
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
        status: list[Literal["scheduled", "released", "ready", "active", "finished", "canceled"]] | None = None,
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
        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_sm37_lookup")
        except ValueError as e:
            return SM37JobListResult.failure(
                error=f"Session error: {e}",
                jobs=[],
                job_count=0,
                filters_applied={},
                retrieved_at=datetime.now(UTC),
            )

        result = await _execute_sm37_lookup(
            page=page,
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
