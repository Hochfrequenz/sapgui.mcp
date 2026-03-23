"""SAP GUI Scripting error hierarchy."""

__all__ = [
    "ElementNotFoundError",
    "SapConnectionError",
    "SapGuiError",
    "SapGuiTimeoutError",
    "ScriptingDisabledError",
]


class SapGuiError(Exception):
    """Base exception for all SAP GUI Scripting errors."""


class SapConnectionError(SapGuiError):
    """Raised when a SAP connection cannot be established or is lost."""


class ScriptingDisabledError(SapGuiError):
    """Raised when SAP GUI Scripting is not enabled on the server."""


class ElementNotFoundError(SapGuiError):
    """Raised when a GUI element cannot be found by ID or name."""


class SapGuiTimeoutError(SapGuiError):
    """Raised when an operation exceeds the allowed timeout."""
