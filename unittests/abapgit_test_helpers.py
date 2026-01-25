"""
Helper utilities for abapGit integration tests.

This module provides:
- Git operations for test submodules (modify, commit, push)
- SE38 verification (read ABAP report source code)

Environment variables:
- SAP_TEST_TRANSPORT: Transport request to use for test repos (default: S4UK902008)
"""

import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

ABAPGIT_REPOS_DIR = Path(__file__).parent / "abapgit_repos"

# Test repository configurations
# Transport request can be overridden via SAP_TEST_TRANSPORT environment variable
DEFAULT_TRANSPORT = os.environ.get("SAP_TEST_TRANSPORT", "S4UK902008")

TEST_REPOS = {
    "private": {
        "name": "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY",
        "report": "Z_REPORT_IN_PRIVATE_GIT_REPO",
        "file": "src/z_report_in_private_git_repo.prog.abap",
        "trkorr": DEFAULT_TRANSPORT,
    },
    "public": {
        "name": "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
        "report": "Z_REPORT_IN_PUBLIC_GIT_REPO",
        "file": "src/z_report_in_public_git_repo.prog.abap",
        "trkorr": DEFAULT_TRANSPORT,
    },
}


def get_repo_path(repo_type: str) -> Path:
    """Get the filesystem path to a test repository submodule."""
    repo_config = TEST_REPOS.get(repo_type)
    if not repo_config:
        raise ValueError(f"Unknown repo type: {repo_type}. Use 'private' or 'public'.")
    return ABAPGIT_REPOS_DIR / repo_config["name"]


def get_report_file_path(repo_type: str) -> Path:
    """Get the path to the ABAP report file in a test repository."""
    repo_config = TEST_REPOS[repo_type]
    return get_repo_path(repo_type) / repo_config["file"]


def generate_test_marker() -> str:
    """Generate a unique marker string for this test run."""
    now = datetime.now()
    short_uuid = str(uuid.uuid4())[:8]
    return f"TEST-{now.strftime('%Y%m%d-%H%M%S')}-{short_uuid}"


def create_abap_report_content(repo_type: str, test_marker: str) -> str:
    """
    Generate ABAP report source code with a unique test marker.

    Args:
        repo_type: 'private' or 'public'
        test_marker: Unique string to identify this test run

    Returns:
        Complete ABAP report source code
    """
    repo_config = TEST_REPOS[repo_type]
    report_name = repo_config["report"]
    label = "PRIVATE" if repo_type == "private" else "PUBLIC"

    return f"""*&---------------------------------------------------------------------*
*& Report {report_name}
*&---------------------------------------------------------------------*
*&
*&---------------------------------------------------------------------*
REPORT {report_name}.
WRITE 'HELLO {label} REPO - {test_marker}'.
"""


def modify_test_repo(repo_type: str, test_marker: str) -> str:
    """
    Modify the ABAP report in a test repository with a unique marker.

    Args:
        repo_type: 'private' or 'public'
        test_marker: Unique string to identify this test run

    Returns:
        The expected WRITE statement text that should appear in SE38
    """
    repo_config = TEST_REPOS[repo_type]
    label = "PRIVATE" if repo_type == "private" else "PUBLIC"

    # Generate the new content
    content = create_abap_report_content(repo_type, test_marker)

    # Write to the file
    report_path = get_report_file_path(repo_type)
    report_path.write_text(content, encoding="utf-8")

    # Return the expected text that should appear in SE38
    return f"HELLO {label} REPO - {test_marker}"


def git_commit_and_push(repo_type: str, message: str | None = None) -> tuple[bool, str]:
    """
    Commit changes and push to the remote repository.

    Args:
        repo_type: 'private' or 'public'
        message: Optional commit message (auto-generated if not provided)

    Returns:
        Tuple of (success: bool, output: str)
    """
    repo_path = get_repo_path(repo_type)

    if message is None:
        message = f"test: update report for MCP integration test {datetime.now().isoformat()}"

    try:
        # Stage all changes
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on "nothing to commit"
        )

        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            return False, f"Commit failed: {result.stderr}"

        # Push
        result = subprocess.run(
            ["git", "push"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        return True, result.stdout + result.stderr

    except subprocess.CalledProcessError as e:
        return False, f"Git operation failed: {e.stderr}"
    except Exception as e:
        return False, f"Error: {e}"


def git_get_current_commit(repo_type: str) -> str | None:
    """Get the current commit SHA of a test repository."""
    repo_path = get_repo_path(repo_type)

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def read_current_report_content(repo_type: str) -> str | None:
    """Read the current content of the ABAP report file."""
    report_path = get_report_file_path(repo_type)
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return None


def extract_write_text_from_abap(content: str) -> str | None:
    """
    Extract the text from a WRITE statement in ABAP code.

    Args:
        content: ABAP source code

    Returns:
        The text in single quotes from the WRITE statement, or None
    """
    import re

    # Match WRITE 'text'. or WRITE: 'text'.
    match = re.search(r"WRITE[:\s]+'([^']+)'", content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None
