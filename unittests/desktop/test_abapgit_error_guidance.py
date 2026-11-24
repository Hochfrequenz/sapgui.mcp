"""abapGit error guidance and the status of a pull with an empty status bar (unit tests, no SAP)."""

from types import SimpleNamespace

import pytest

from sapguimcp import lang
from sapguimcp.tools.abapgit_tools import (
    _analyze_pull_result,
    _enrich_transport_error,
    _is_credentials_popup_error,
    _is_no_task_error,
    _is_transport_required_error,
)


def test_is_transport_required_error() -> None:
    """Test detection of transport-required error messages."""
    # Positive cases — various SAP transport error messages
    assert _is_transport_required_error("Transport required. Provide P_TRKORR= KS")
    assert _is_transport_required_error("transport erforderlich")
    assert _is_transport_required_error("Transport Required")
    assert _is_transport_required_error("Please provide P_TRKORR= for this operation")
    assert _is_transport_required_error("Transportauftrag fehlt")

    # Negative cases — unrelated errors
    assert not _is_transport_required_error("Repository not found")
    assert not _is_transport_required_error("Pull successful")
    assert not _is_transport_required_error("Authentication failed")
    assert not _is_transport_required_error("")


def test_enrich_transport_error_adds_guidance() -> None:
    """Test that transport errors get actionable guidance appended."""
    # Transport error should get guidance
    enriched = _enrich_transport_error("Transport required. Provide P_TRKORR= KS")
    assert "Transport required" in enriched
    assert "SE09" in enriched
    assert "trkorr=" in enriched

    # Non-transport error should pass through unchanged
    original = "Repository not found"
    assert _enrich_transport_error(original) == original


def test_enrich_transport_error_strips_trailing_period() -> None:
    """Test that enriched error does not produce double-period sentence boundary."""
    enriched = _enrich_transport_error("Transport required.")
    # Should not have ". ." or ".." at the junction (but "..." in repo=... is fine)
    assert ". ." not in enriched, f"Double period at sentence boundary in: {enriched}"
    # The original trailing period should be stripped before appending guidance
    assert not enriched.startswith("Transport required.. "), f"Trailing period not stripped: {enriched}"

    enriched2 = _enrich_transport_error("Transport required. Provide P_TRKORR= KS.")
    assert ". ." not in enriched2, f"Double period at sentence boundary in: {enriched2}"


def test_enrich_transport_error_german() -> None:
    """Test that German transport errors also get guidance."""
    enriched = _enrich_transport_error("Transport erforderlich")
    assert "SE09" in enriched
    assert "trkorr=" in enriched


@pytest.mark.parametrize(
    "message",
    [
        # German status bar text, cut at 50 characters by the report's MESSAGE ... WITH parameter
        "Formaufruf fehlgeschlagen: Form PASSWORD_POPUP kon",
        "Could not find the form PASSWORD_POPUP in program Z_REPORT",
        # English text as cut in the field report
        "Could not find the form PA",
    ],
)
def test_credentials_popup_error_is_recognised_and_enriched(message: str) -> None:
    """abapGit's password popup cannot work through the API: point at the token, not at the OK-code path."""
    assert _is_credentials_popup_error(message)
    enriched = _enrich_transport_error(message)
    assert enriched.startswith(message.rstrip(". "))
    assert "ABAPGIT_PAT" in enriched
    assert "GITHUB_PAT" in enriched
    assert "`pat`" in enriched  # an explicit argument takes precedence over the environment variables
    assert ". ." not in enriched


@pytest.mark.parametrize(
    "message",
    [
        "Repository not found",
        "Transport required. Provide P_TRKORR= KS",
        "Could not find the form PERFORM_X",
        "Could not find the form PAYMENT_X",
        "Could not find the form PA_SOMETHING",
        "",
    ],
)
def test_credentials_popup_error_does_not_match_other_errors(message: str) -> None:
    """Unrelated errors must not get the credentials hint."""
    assert not _is_credentials_popup_error(message)
    assert "ABAPGIT_PAT" not in _enrich_transport_error(message)


class _EmptyStatusBackend:
    """Minimal backend whose status bar stays empty (an empty bar was also seen after a successful pull)."""

    async def get_status_bar(self) -> SimpleNamespace:
        return SimpleNamespace(message="", type="none")

    async def wait_for_ready(self, **_kwargs: int) -> None:
        return None

    async def get_snapshot(self) -> str:
        return ""


@pytest.mark.anyio
async def test_pull_with_empty_status_bar_says_it_may_have_run() -> None:
    """'Status unknown' must not read like a failure that definitely did not pull."""
    result = await _analyze_pull_result(_EmptyStatusBackend(), "some_repo", lang.view_for("DE"))  # type: ignore[arg-type]
    assert result.success is False
    assert result.error is not None
    assert "status unknown" in result.error.lower()
    assert "may have run" in result.error
    assert "abapGit" in result.error
    assert "ABAPGIT_PAT" in result.error
    assert "`pat`" in result.error


def test_is_no_task_error() -> None:
    """Test detection of no-task-in-transport error messages."""
    # Positive cases
    assert _is_no_task_error("User TESTUSER has no modifiable task in XYZK900011")
    assert _is_no_task_error("Benutzer TESTUSER hat keine modifizierbare Aufgabe")
    assert _is_no_task_error("has no task in transport")

    # Negative cases
    assert not _is_no_task_error("Transport required. Provide P_TRKORR=")
    assert not _is_no_task_error("Pull successful")
    assert not _is_no_task_error("")


def test_enrich_no_task_error_adds_guidance() -> None:
    """Test that no-task errors get actionable guidance appended."""
    enriched = _enrich_transport_error("User TESTUSER has no modifiable task in XYZK900011")
    assert "has no modifiable task" in enriched
    assert "SE09" in enriched
    assert "task" in enriched.lower()

    # Non-task error should pass through unchanged
    original = "Repository not found"
    assert _enrich_transport_error(original) == original
