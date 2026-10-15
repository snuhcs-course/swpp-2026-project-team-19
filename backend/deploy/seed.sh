#!/usr/bin/env bash
# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-15). Reviewed by Haeul Yang.
# Load the catalog seed (scripts/seed_catalog.py) into this server's database.
#
# Run by the seed-only SSH key, whose authorized_keys line forces this script (DEPLOY.md, section 5).
# The command the client sent arrives in SSH_ORIGINAL_COMMAND and must be exactly:
#   dry-run   load, print the counts, roll back
#   apply     load and commit
# It uses the code already deployed here (no git pull), so the seed matches the running API.
set -euo pipefail

# A command run over SSH skips the login profile that puts uv on PATH.
export PATH="$HOME/.local/bin:$PATH"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mode="${SSH_ORIGINAL_COMMAND:-${1:-}}"
case "$mode" in
	dry-run) flags=(--dry-run) ;;
	apply) flags=() ;;
	*)
		echo "usage: dry-run | apply (got '${mode}')" >&2
		exit 2
		;;
esac

echo "==> seed ($mode) with code $(git log --oneline -1)"
uv run --no-sync --env-file .env python scripts/seed_catalog.py "${flags[@]}"
