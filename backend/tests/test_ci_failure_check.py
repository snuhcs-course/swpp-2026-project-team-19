# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-21). Reviewed by Haeul Yang.
"""Deliberately failing test for I2-P39: shows that a failing backend test fails the PR check.

This branch is never merged; the PR is closed after the failed run is recorded.
"""


def test_a_failing_test_fails_the_backend_check():
    assert 1 + 1 == 3, "deliberate failure to verify that Backend CI/CD reports a failed check"
