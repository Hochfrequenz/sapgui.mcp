"""GuiOkCodeField — the command/transaction input field."""

from __future__ import annotations

from sapsucker.components.base import GuiVComponent

__all__ = ["GuiOkCodeField"]


class GuiOkCodeField(GuiVComponent):
    """Wraps the COM GuiOkCodeField interface (TypeAsNumber 35).

    The OK-code (command) field at the top of the SAP GUI window.
    To execute a transaction, set .text to the command string
    (e.g. '/nSE38') and then call window.send_v_key(0) to press Enter.
    """

    @property
    def is_list_element(self) -> bool:
        """Whether this field belongs to a list."""
        return bool(self._com.IsListElement)
