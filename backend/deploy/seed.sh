#!/usr/bin/env bash
# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-15). Reviewed by Haeul Yang.
# Modified with Claude Code (Jinwoo Park, 2026-10-19): demo-menus-dry-run / demo-menus-apply modes.
# Load the catalog seed (scripts/seed_catalog.py) into this server's database.
#
# Run by the seed-only SSH key, whose authorized_keys line forces this script (DEPLOY.md, section 5).
# The command the client sent arrives in SSH_ORIGINAL_COMMAND and must be exactly:
#   dry-run   load, print the counts, roll back
#   apply     load and commit
#   demo-menus-dry-run / demo-menus-apply
#             only the demo menu boards (ai/catalog/menu_seed_*_demo_v1.json, scripts/seed_menu.py):
#             each file replaces that bar's current menu board, one transaction per file.
#             Separate from dry-run/apply so a catalog seed never resets published menus.
# It uses the code already deployed here (no git pull), so the seed matches the running API.
set -euo pipefail

# A command run over SSH skips the login profile that puts uv on PATH.
export PATH="$HOME/.local/bin:$PATH"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mode="${SSH_ORIGINAL_COMMAND:-${1:-}}"
case "$mode" in
	dry-run | demo-menus-dry-run) flags=(--dry-run) ;;
	apply | demo-menus-apply) flags=() ;;
	*)
		echo "usage: dry-run | apply | demo-menus-dry-run | demo-menus-apply (got '${mode}')" >&2
		exit 2
		;;
esac

echo "==> seed ($mode) with code $(git log --oneline -1)"
case "$mode" in
	demo-menus-*)
		shopt -s nullglob
		menus=(../ai/catalog/menu_seed_*_demo_v1.json)
		if [ ${#menus[@]} -eq 0 ]; then
			echo "no demo menu seed files found" >&2
			exit 1
		fi
		for menu in "${menus[@]}"; do
			uv run --no-sync --env-file .env python scripts/seed_menu.py --menu "$menu" "${flags[@]}"
		done
		;;
	*)
		uv run --no-sync --env-file .env python scripts/seed_catalog.py "${flags[@]}"
		;;
esac
