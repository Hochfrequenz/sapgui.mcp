"""The date format of the logged-on SAP user (SU3, Defaults tab), derived from a date a field already shows (#1043).

SAP types dates in the format of the *user* (``USR01-DATFM``), not in the one of the logon language: a DE user may well
have ``MM/DD/YYYY``. The selection screens of SM37, SLG1 and ST22 pre-fill their date field, so the format is read off
that field by its shape: the separator and whether the four-digit year comes first or last tell SAP's six Gregorian
formats apart, whatever the date is (no comparison with the local "today", whose time zone may differ from the SAP
server's). The result is cached per session and falls back to the logon-language default (with a warning) when it
cannot be derived.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

#: SAP's Gregorian date formats (``USR01-DATFM`` 1 to 6): the shape of a shown date -> ``strftime`` pattern. The
#: separator and the position of the four-digit year identify each format uniquely.
_USER_DATE_FORMATS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\d{2}\.\d{2}\.\d{4}"), "%d.%m.%Y"),  # DD.MM.YYYY
    (re.compile(r"\d{2}/\d{2}/\d{4}"), "%m/%d/%Y"),  # MM/DD/YYYY
    (re.compile(r"\d{2}-\d{2}-\d{4}"), "%m-%d-%Y"),  # MM-DD-YYYY
    (re.compile(r"\d{4}\.\d{2}\.\d{2}"), "%Y.%m.%d"),  # YYYY.MM.DD
    (re.compile(r"\d{4}/\d{2}/\d{2}"), "%Y/%m/%d"),  # YYYY/MM/DD
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "%Y-%m-%d"),  # YYYY-MM-DD
)

#: Years outside this range are not Gregorian dates of a selection screen: SAP's Japanese and Islamic formats
#: (``DATFM`` 7 to C) share the shapes above with another year count, and typing a Gregorian date there would be wrong.
_PLAUSIBLE_YEARS = range(1900, 2101)


def derive_date_format(shown: str | None) -> str | None:
    """
    The ``strftime`` pattern of the date a field shows, or ``None`` when it cannot be told.

    ``None`` is returned for an empty field, a value that is not a valid date in one of SAP's six Gregorian formats,
    and a year outside 1900 to 2100 (a non-Gregorian format): the caller then falls back to the logon-language default.
    """
    text = (shown or "").strip()
    for shape, pattern in _USER_DATE_FORMATS:
        if shape.fullmatch(text):
            try:
                parsed = datetime.strptime(text, pattern)
            except ValueError:
                return None
            return pattern if parsed.year in _PLAUSIBLE_YEARS else None
    return None


async def resolve_user_date_format(backend: Any, field_names: Sequence[str], fallback: str) -> str:
    """
    The ``strftime`` pattern for typing a date into *field_names* on the current session of *backend*.

    Reads the first of *field_names* that shows a value (call this BEFORE the field is overwritten) and caches what it
    derives per session. Falls back to *fallback*, the logon-language default, with a logged warning when the format
    cannot be derived. A fallback is not cached, so the next call tries again.
    """
    try:
        cached = backend.cached_date_format()
        if isinstance(cached, str) and cached:
            return cached
        shown = await backend.read_field_text(field_names)
        derived = derive_date_format(shown if isinstance(shown, str) else None)
        if derived is not None:
            backend.cache_date_format(derived)
            return derived
        reason = "the date field is empty or does not show a Gregorian date"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        reason = f"the date field could not be read ({type(exc).__name__})"
    logger.warning(
        "could not derive the user's date format, falling back to the logon-language default",
        extra={"fallback": fallback, "reason": reason, "fields": list(field_names)},
    )
    return fallback
