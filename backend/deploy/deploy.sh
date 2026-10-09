#!/usr/bin/env bash
# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #16, #18). Reviewed by Haeul Yang.
# Redeploy on the server: update the code, install dependencies, migrate, restart, check.
#
#   ~/swpp-2026-project-team-19/backend/deploy/deploy.sh            # current branch
#   ~/swpp-2026-project-team-19/backend/deploy/deploy.sh main       # switch to a branch first
set -euo pipefail

# A command run over SSH (automatic deployment) skips the login profile that puts uv on PATH.
export PATH="$HOME/.local/bin:$PATH"

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
echo "==> code: $branch"
git fetch origin
git checkout "$branch"
git pull --ff-only origin "$branch"

echo "==> dependencies"
uv sync --frozen --no-dev

echo "==> migrations"
uv run --no-sync --env-file .env alembic upgrade head

echo "==> restart"
sudo systemctl restart bottlemap-api

for _ in $(seq 1 30); do
	if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
		echo "==> healthy: $(git log --oneline -1)"
		exit 0
	fi
	sleep 1
done
echo "API did not become healthy; recent logs:" >&2
sudo journalctl -u bottlemap-api -n 50 --no-pager >&2
exit 1
