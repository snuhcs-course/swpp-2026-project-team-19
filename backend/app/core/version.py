# AI-generated with ChatGPT (Haeul Yang, 2026-10-07, PR #19). Reviewed by Haeul Yang.
"""The commit this process runs, reported by /health so a deployment can be checked from outside."""

import subprocess
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def read_commit(directory: Path) -> str | None:
    """Short hash of the checked-out commit, or None when there is no git checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


@lru_cache(maxsize=1)
def get_version() -> str | None:
    """Read once, at start-up: a later `git pull` without a restart does not change the running code."""
    return read_commit(BACKEND_DIR)
