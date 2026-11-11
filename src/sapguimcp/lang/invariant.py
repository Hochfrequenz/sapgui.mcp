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
    abapgit_pull_successful: Text
    """Success message of the abapGit pull report (our own Z report, English only)."""
    abapgit_successful: Text
    abapgit_branch_not_found: Text
    """Prefix of the report's branch error; matched with ``startswith``, so case-sensitive."""
    abapgit_key_not_found: Text
    """The report's answer to an unknown repository key."""
    abapgit_error_words: Text
    """English words in abapGit's own exception texts (popups); the logon language does not translate them."""
    abapgit_error: Text
    abapgit_screen_errors: Text
    abapgit_trkorr_hint: Text
    """The report names its transport parameter ``P_TRKORR`` in its transport hint."""


INVARIANT = Invariant(
    sm34_hint=Text(("SM34",)),
    abapgit_pull_successful=Text(("pull successful",)),
    abapgit_successful=Text(("successful",)),
    abapgit_branch_not_found=Text(("Branch not found:",), fold=False),
    abapgit_key_not_found=Text(("repository not found: key",)),
    abapgit_error_words=Text(("error", "exception", "failed", "required", "transport", "repository")),
    abapgit_error=Text(("error",)),
    abapgit_screen_errors=Text(("repository not found", "exception", "error:")),
    abapgit_trkorr_hint=Text(("provide p_trkorr", "p_trkorr=")),
)
