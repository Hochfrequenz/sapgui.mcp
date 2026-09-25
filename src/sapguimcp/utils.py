"""Shared utility functions for SAP WebGUI MCP."""

import json
import logging
import os
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

SapLanguage = Literal["DE", "EN"]


def as_sap_language(value: str) -> SapLanguage:
    """Narrow a configured language string to the two values date formatting handles.

    ``sap-mcp-config`` still guarantees a system's language is ``DE`` or ``EN``,
    but since 1.1.0 it *types* the field as ``str``: the check moved off the
    field onto the ``Config`` model validator, so that one invalid language no
    longer aborts validation and hides every other error.  That leaves the
    static type too wide to assign straight to :data:`SapLanguage`.

    Narrowing at runtime rather than with a ``cast`` keeps this correct even if
    the upstream guarantee changes again.  Anything unrecognised becomes ``EN``,
    which is the same default the config layer applies for a missing language —
    but it is logged, because an EN fallback formats dates as ``MM/DD/YYYY``,
    and typing that into a DE selection screen silently selects the wrong range.
    """
    normalized = value.strip().upper()
    if normalized == "DE":
        return "DE"
    if normalized != "EN":
        logger.warning(
            "unexpected configured language, falling back to EN",
            extra={"language": value},
        )
    return "EN"


def format_sap_date(iso_date: str, language: SapLanguage) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to SAP locale format.

    Args:
        iso_date: Date string in YYYY-MM-DD format (e.g., "2026-02-22")
        language: SAP language code ("DE" or "EN")

    Returns:
        Formatted date string:
        - DE: DD.MM.YYYY (e.g., "22.02.2026")
        - EN: MM/DD/YYYY (e.g., "02/22/2026")

    Raises:
        ValueError: If iso_date is not in YYYY-MM-DD format
    """
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Expected YYYY-MM-DD format, got: {iso_date}") from e

    if language == "DE":
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%m/%d/%Y")


def resolve_output_file_path(output_file: str, base_dir: Path | None = None) -> Path:
    """Resolve ``output_file`` within a safe base directory.

    Relative paths are resolved against ``base_dir`` (or the current working
    directory by default). Absolute paths are allowed only when they already
    resolve inside that same base directory.
    """
    safe_base_dir = (base_dir or Path.cwd()).expanduser().resolve()
    candidate = Path(output_file).expanduser()

    if candidate.is_absolute():
        try:
            relative_path = candidate.relative_to(safe_base_dir)
        except ValueError as e:
            raise ValueError(
                f"output_file must stay within the working directory: {safe_base_dir}"
            ) from e
    else:
        relative_path = candidate

    return safe_base_dir / _normalize_relative_output_path(relative_path)


def _normalize_relative_output_path(path: Path) -> Path:
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError("output_file must stay within the working directory")
            parts.pop()
            continue
        parts.append(part)

    if not parts:
        raise ValueError("output_file must name a file")

    return Path(*parts)


def _reject_symlink_path_components(path: Path, safe_base_dir: Path) -> None:
    current_path = safe_base_dir
    for part in path.relative_to(safe_base_dir).parts:
        current_path /= part
        if current_path.exists() and current_path.is_symlink():
            raise ValueError("output_file must not traverse symlinks")


def write_json_output_file(output_file: str, payload: Any, base_dir: Path | None = None) -> Path:
    """Write JSON output to a sandboxed ``output_file`` path."""
    safe_base_dir = (base_dir or Path.cwd()).expanduser().resolve()
    output_path = resolve_output_file_path(output_file, base_dir)
    relative_output_path = output_path.relative_to(safe_base_dir)
    nofollow_flag = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)

    if nofollow_flag is None or directory_flag is None:
        _reject_symlink_path_components(output_path.parent, safe_base_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path_components(output_path.parent, safe_base_dir)
        if output_path.exists() and output_path.is_symlink():
            raise ValueError("output_file must not traverse symlinks")
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return output_path

    current_directory_fd = os.open(safe_base_dir, os.O_RDONLY | directory_flag)
    base_directory_fd = current_directory_fd

    try:
        for part in relative_output_path.parts[:-1]:
            try:
                os.mkdir(part, dir_fd=current_directory_fd)
            except FileExistsError:
                pass
            try:
                next_directory_fd = os.open(
                    part,
                    os.O_RDONLY | directory_flag | nofollow_flag,
                    dir_fd=current_directory_fd,
                )
            except OSError as e:
                raise ValueError("output_file must not traverse symlinks") from e
            if current_directory_fd != base_directory_fd:
                os.close(current_directory_fd)
            current_directory_fd = next_directory_fd

        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | nofollow_flag
        try:
            file_descriptor = os.open(
                relative_output_path.name,
                flags,
                0o666,
                dir_fd=current_directory_fd,
            )
        except OSError as e:
            raise ValueError("output_file must not traverse symlinks") from e

        try:
            file_handle = os.fdopen(file_descriptor, "w", encoding="utf-8")
        except Exception:
            os.close(file_descriptor)
            raise

        with file_handle as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    finally:
        if current_directory_fd != base_directory_fd:
            with suppress(OSError):
                os.close(current_directory_fd)
        with suppress(OSError):
            os.close(base_directory_fd)

    return output_path
