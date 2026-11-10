"""Live tests: every desktop session knows its own logon language (#1044, phase 1).

The module's ``backend`` fixture logs on in the default system's configured language. The tests
then open a second connection in the *other* language (DE <-> EN) and check that each session keeps
its own language: in the registry, in the context variable that tool calls see, and inside COM
closures on the worker thread.
"""

import sys
from datetime import date

import pytest

from sapguimcp.backend.desktop import _current_session_id
from sapguimcp.session_language import current_language, normalize_language, use_language
from sapguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _configured_system():  # type: ignore[no-untyped-def]
    from sapguimcp.models.config import get_sap_config  # noqa: PLC0415

    return get_sap_config().get_default()


@skip_no_sap
@pytest.mark.anyio
async def test_login_records_the_logon_language(backend):
    """The fixture's login stored the language SAP reports for the session."""
    sid = backend.registry.primary_session
    expected = normalize_language(_configured_system().language)
    assert backend.registry.language_of(sid) == expected
    reported = await backend.com.run(lambda: str(backend.registry.get_session(sid).info.language))
    assert normalize_language(reported) == expected


@skip_no_sap
@pytest.mark.anyio
async def test_com_closure_sees_the_callers_language(backend):
    """A closure on the COM worker thread sees the caller's session language."""
    sid = backend.registry.primary_session
    with use_language(backend.registry.language_of(sid)):
        assert await backend.com.run(current_language) == backend.registry.language_of(sid)


@skip_no_sap
@pytest.mark.anyio
async def test_second_login_in_the_other_language(backend):
    """A second connection in the other language keeps its own language next to the first one."""
    system = _configured_system()
    first_sid = backend.registry.primary_session
    first_language = backend.registry.language_of(first_sid)
    other = "EN" if first_language == "DE" else "DE"

    with use_language(None):
        result = await backend.login(
            "x",
            system.user,
            system.password.get_secret_value(),
            system.client,
            other,
            connection_name=system.connection_name,
        )
        assert result.success, f"Login failed: {result.error}"
        assert current_language() == other, "login sets the language for the rest of the tool call"

    second_sid = result.session_id
    assert backend.registry.language_of(second_sid) == other
    assert backend.registry.language_of(first_sid) == first_language
    reported = await backend.com.run(lambda: str(backend.registry.get_session(second_sid).info.language))
    assert normalize_language(reported) == other

    try:
        # Each session, addressed the way the backend manager does it, works in its own language.
        for sid, language in ((second_sid, other), (first_sid, first_language)):
            token = _current_session_id.set(sid)
            try:
                with use_language(backend.registry.language_of(sid)):
                    assert await backend.com.run(current_language) == language
                    result = await _execute_sm37_lookup_desktop(
                        backend, job_name="*", username=None, statuses=None, from_date=None, to_date=None
                    )
                    assert result.success, f"SM37 in {language} failed: {result.error}"
                    await go_home(backend)
            finally:
                _current_session_id.reset(token)
    finally:
        # Close the extra connection here rather than in the module teardown: closing several
        # connections in one teardown destabilises SAP GUI scripting for the next module (#399).
        await backend.close_session(second_sid)
        assert backend.registry.language_of(second_sid) is None


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_date_range_in_the_session_language(backend):
    """SM37 with today's date as range, typed in the format of the primary session's language."""
    sid = backend.registry.primary_session
    today = date.today().isoformat()
    token = _current_session_id.set(sid)
    try:
        with use_language(backend.registry.language_of(sid)):
            result = await _execute_sm37_lookup_desktop(
                backend, job_name="*", username=None, statuses=None, from_date=today, to_date=today
            )
    finally:
        _current_session_id.reset(token)
    # An empty job list is still success=True; a date typed in the wrong format is not.
    assert result.success, f"SM37 date range failed: {result.error}"
    await go_home(backend)
