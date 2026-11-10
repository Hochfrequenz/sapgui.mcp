"""Texts that are the same in every SAP logon language (#1044).

Only text that is fixed regardless of the logon language belongs here: transaction codes in
messages, abapGit's English-only UI, the output of our own Z report. SAP-translated texts that
merely coincide in DE and EN (``Interface``) stay in the packs, because a third language may
differ. Fields are added by the phase-3 migrations.
"""

from dataclasses import dataclass

from sapguimcp.lang.text import Text


@dataclass(frozen=True, slots=True)
class Invariant:
    """Language-independent texts; exported as the constant ``lang.INVARIANT``."""

    sm34_hint: Text
    """SM30 points to SM34 for view clusters; the transaction code is not translated."""


INVARIANT = Invariant(
    sm34_hint=Text(("SM34",)),
)
