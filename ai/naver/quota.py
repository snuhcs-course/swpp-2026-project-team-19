# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P28). Reviewed by Jinwoo Park.
"""Stop all Gemini work at the first quota error (overnight rule, 2026-10-15).

    judge = GuardedJudge(budget=200)   # judge.Judge, but a 429 / RESOURCE_EXHAUSTED is not retried:
                                       # it writes the stop file and raises QuotaStop
    check_quota_stop()                 # raises QuotaStop if an earlier task hit the quota

The stop file lives in the data dir (outside the repo) so later tasks in the same night
see it. It holds the time and the task name only, never request content or keys.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import data_dir  # noqa: E402
from judge import Judge  # noqa: E402

STOP_FILE_NAME = "gemini_quota_stop.json"


class QuotaStop(RuntimeError):
    pass


def stop_file() -> Path:
    return data_dir() / STOP_FILE_NAME


def is_quota_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}"
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code == 429 or "429" in text or "RESOURCE_EXHAUSTED" in text


def check_quota_stop() -> None:
    path = stop_file()
    if path.exists():
        raise QuotaStop(f"Gemini quota stop recorded earlier: {path.read_text(encoding='utf-8')}")


def record_quota_stop(task: str, exc: Exception) -> None:
    path = stop_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task": task,
                                "error": f"{type(exc).__name__}: {str(exc)[:200]}"}, ensure_ascii=False),
                    encoding="utf-8")


class GuardedJudge(Judge):
    """judge.Judge with the quota rule. Prompt, model and request are unchanged."""

    def __init__(self, *args, task: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task

    def _call(self, request: dict):
        check_quota_stop()
        try:
            return super()._call(request)
        except QuotaStop:
            raise
        except Exception as exc:
            if is_quota_error(exc):
                record_quota_stop(self.task, exc)
                raise QuotaStop(f"{self.task}: {type(exc).__name__} {str(exc)[:200]}") from exc
            raise


# judge.Judge._call retries every transient error, 429 included. Wrap the module's
# _is_transient so a quota error is never retried (it then propagates to GuardedJudge._call).
import judge as _judge_module  # noqa: E402

_orig_is_transient = _judge_module._is_transient


def _is_transient_no_quota(exc: Exception) -> bool:
    return False if is_quota_error(exc) else _orig_is_transient(exc)


_judge_module._is_transient = _is_transient_no_quota
