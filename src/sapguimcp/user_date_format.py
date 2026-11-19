"""The date format of the logged-on SAP user (SU3, Defaults tab), derived from a date field that shows today (#1043).

SAP types dates in the format of the *user* (``USR01-DATFM``), not in the one of the logon language: a DE user may well
have ``MM/DD/YYYY``. The selection screens of SM37, SLG1 and ST22 pre-fill their date field with today's date, so the
format is read off that field: the order of day, month and year and the separator. The result is cached per session
and falls back to the logon-language default (with a warning) when it cannot be derived.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

#: The date formats of SAP (``USR01-DATFM`` 1 to 6) as ``strftime`` patterns.
_USER_DATE_FORMATS: tuple[str, ...] = (
    "%d.%m.%Y",  # DD.MM.YYYY
    "%m/%d/%Y",  # MM/DD/YYYY
    "%m-%d-%Y",  # MM-DD-YYYY
    "%Y.%m.%d",  # YYYY.MM.DD
    "%Y/%m/%d",  # YYYY/MM/DD
    "%Y-%m-%d",  # YYYY-MM-DD
)


def derive_date_format(shown: str | None, today: date) -> str | None:
    """
    The ``strftime`` pattern in which a date field shows today's date, or ``None`` when it cannot be told.

    ``None`` is returned for an empty field and for a date that is not today's: the caller then falls back to the
    logon-language default. Each of the six SAP formats has its own separator/order, so matching the exact string
    resolves even a day that equals the month.
    """
    text = (shown or "").strip()
    if not text:
        return None
    matches = [pattern for pattern in _USER_DATE_FORMATS if today.strftime(pattern) == text]
    return matches[0] if len(matches) == 1 else None


async def resolve_user_date_format(
    backend: Any, field_names: Sequence[str], fallback: str, *, today: date | None = None
) -> str:
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
        derived = derive_date_format(shown if isinstance(shown, str) else None, today or date.today())
        if derived is not None:
            backend.cache_date_format(derived)
            return derived
        reason = "the date field is empty or does not show today"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        reason = f"the date field could not be read ({type(exc).__name__})"
    logger.warning(
        "could not derive the user's date format, falling back to the logon-language default",
        extra={"fallback": fallback, "reason": reason, "fields": list(field_names)},
    )
    return fallback
