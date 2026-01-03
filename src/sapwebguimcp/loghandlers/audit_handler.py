"""Audit log handler for intent logging."""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path


class IntentFileHandler(logging.Handler):
    """Handler that writes INTENT log entries to session-specific JSONL files.

    Only processes log records that start with "INTENT |".
    Creates files in format: audit_YYYYMMDDTHHMMSS_{session_id}.jsonl
    """

    # Pattern to parse INTENT log messages
    _INTENT_PATTERN = re.compile(
        r"INTENT \| session=(?P<session_id>\S+) \| entry_id=(?P<entry_id>\S+) \| "
        r"(?P<intent>.+?) \| context=\{(?P<context>.*)\}$"
    )

    def __init__(self, log_dir: Path) -> None:
        """Initialize the handler.

        Args:
            log_dir: Directory to write audit log files to
        """
        super().__init__()
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._session_files: dict[str, Path] = {}

    def _get_session_file(self, session_id: str) -> Path:
        """Get or create the log file for a session."""
        if session_id not in self._session_files:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            filename = f"audit_{timestamp}_{session_id}.jsonl"
            self._session_files[session_id] = self.log_dir / filename
        return self._session_files[session_id]

    def emit(self, record: logging.LogRecord) -> None:
        """Write an INTENT log record to the appropriate file."""
        message = record.getMessage()
        if not message.startswith("INTENT |"):
            return

        match = self._INTENT_PATTERN.match(message)
        if not match:
            return

        session_id = match.group("session_id")
        entry_id = match.group("entry_id")
        intent = match.group("intent")
        context_str = match.group("context")

        # Parse context
        context: dict[str, str] = {}
        if context_str:
            for pair in context_str.split(", "):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    context[key] = value

        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "session_id": session_id,
            "entry_id": entry_id,
            "intent": intent,
            "context": context,
        }

        try:
            file_path = self._get_session_file(session_id)
            with file_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            self.handleError(record)
