"""
Unit tests for SM37 (Job Overview) parser.

Tests parsing of YAML accessibility snapshots from SM37 job list screens.
These tests run offline against pre-captured snapshots.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.sm37_parser import (
    is_job_list_screen,
    is_no_jobs_found,
    parse_sm37_job_list,
    parse_sm37_job_log,
)

SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "sm37_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run exploration tests first")
    return filepath.read_text(encoding="utf-8")


class TestJobListDetection:
    """Tests for detecting SM37 screen states."""

    def test_detect_job_list_screen(self) -> None:
        snapshot = _load_snapshot("sm37_job_list")
        assert is_job_list_screen(snapshot)

    def test_initial_screen_not_job_list(self) -> None:
        snapshot = _load_snapshot("sm37_initial")
        assert not is_job_list_screen(snapshot)

    def test_no_jobs_found_stays_on_selection(self) -> None:
        """When no jobs found, SAP stays on selection screen with status bar message."""
        snapshot = _load_snapshot("sm37_no_jobs_found")
        assert is_no_jobs_found(snapshot)
        assert not is_job_list_screen(snapshot)


class TestJobListParsing:
    """Tests for parsing SM37 job list."""

    def test_parse_job_list(self) -> None:
        snapshot = _load_snapshot("sm37_job_list")
        jobs = parse_sm37_job_list(snapshot)

        assert len(jobs) > 0, "Should find at least one job"

        first_job = jobs[0]
        assert first_job.job_name, "Job name should not be empty"
        assert first_job.user, "User should not be empty"
        assert first_job.status in (
            "Scheduled",
            "Released",
            "Ready",
            "Active",
            "Finished",
            "Canceled",
        ), f"Unexpected status: {first_job.status}"

    def test_parse_no_jobs(self) -> None:
        snapshot = _load_snapshot("sm37_no_jobs_found")
        jobs = parse_sm37_job_list(snapshot)
        assert len(jobs) == 0

    def test_status_normalization(self) -> None:
        snapshot = _load_snapshot("sm37_job_list")
        jobs = parse_sm37_job_list(snapshot)

        for job in jobs:
            assert job.status in (
                "Scheduled",
                "Released",
                "Ready",
                "Active",
                "Finished",
                "Canceled",
            ), f"Status not normalized: {job.status}"

    def test_deduplication(self) -> None:
        """SM37 sometimes renders each job row twice; parser should deduplicate."""
        snapshot = _load_snapshot("sm37_job_list")
        jobs = parse_sm37_job_list(snapshot)

        # Check that we don't have exact duplicates
        seen = set()
        for job in jobs:
            key = (job.job_name, job.user, job.status, job.start_time, job.mandant)
            assert key not in seen, f"Duplicate job: {key}"
            seen.add(key)

    def test_finished_jobs_have_start_time(self) -> None:
        """Finished jobs should have a start_time with date."""
        snapshot = _load_snapshot("sm37_job_list")
        jobs = parse_sm37_job_list(snapshot)

        finished = [j for j in jobs if j.status == "Finished"]
        for job in finished:
            assert job.start_time is not None, f"Finished job {job.job_name} should have start_time"
            assert "." in job.start_time or "/" in job.start_time, f"Start time should contain a date: {job.start_time}"

    def test_initial_screen_returns_empty(self) -> None:
        """Parsing initial screen should return empty list."""
        snapshot = _load_snapshot("sm37_initial")
        jobs = parse_sm37_job_list(snapshot)
        assert len(jobs) == 0


class TestJobLogParsing:
    """Tests for parsing SM37 job log."""

    _SYNTHETIC_JOB_LOG = """\
- main "Job Log Einträge für Job: TEST_JOB / 12345678":
  - banner:
    - button "Zurück (F3)"
    - heading "Job Log Einträge" [level=1]
  - table:
    - rowgroup:
      - row "Liste":
        - cell "Liste":
          - region "Liste":
            - text: "Zum Auswählen Zeile markieren"
            - text: Job gestartet
            - text: Step 001 gestartet (Programm ZSAMPLE, Variante , Benutzer TESTUSER)
            - text: Step 001 wurde erfolgreich beendet
            - text: Job beendet
"""

    def test_parse_job_log_extracts_lines(self) -> None:
        result = parse_sm37_job_log(self._SYNTHETIC_JOB_LOG, "TEST_JOB")
        assert result.job_name == "TEST_JOB"
        assert len(result.log_lines) >= 3
        assert any("gestartet" in line for line in result.log_lines)
        assert any("beendet" in line for line in result.log_lines)

    def test_parse_job_log_skips_selection_hint(self) -> None:
        result = parse_sm37_job_log(self._SYNTHETIC_JOB_LOG, "TEST_JOB")
        assert not any("Zum Auswählen" in line for line in result.log_lines)

    def test_parse_job_log_empty_snapshot(self) -> None:
        result = parse_sm37_job_log("- main:\n  - heading: No data", "EMPTY")
        assert result.job_name == "EMPTY"
        assert len(result.log_lines) == 0


class TestDateFormatHelper:
    """Tests for the shared date format helper."""

    def test_format_sap_date_de(self) -> None:
        from sapguimcp.utils import format_sap_date

        assert format_sap_date("2026-02-22", "DE") == "22.02.2026"
        assert format_sap_date("2026-01-05", "DE") == "05.01.2026"
        assert format_sap_date("2025-12-31", "DE") == "31.12.2025"

    def test_format_sap_date_en(self) -> None:
        from sapguimcp.utils import format_sap_date

        assert format_sap_date("2026-02-22", "EN") == "02/22/2026"
        assert format_sap_date("2026-01-05", "EN") == "01/05/2026"
        assert format_sap_date("2025-12-31", "EN") == "12/31/2025"

    def test_format_sap_date_invalid(self) -> None:
        from sapguimcp.utils import format_sap_date

        with pytest.raises(ValueError):
            format_sap_date("22.02.2026", "DE")

        with pytest.raises(ValueError):
            format_sap_date("2026/02/22", "EN")

    def test_format_sap_date_rejects_non_date(self) -> None:
        from sapguimcp.utils import format_sap_date

        with pytest.raises(ValueError):
            format_sap_date("not-a-date", "DE")
