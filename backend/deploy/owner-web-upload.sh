#!/usr/bin/env bash
# Put a new owner web build on this server (task A9). The API serves it at /owner/ (app/owner_web).
#
# Run by the upload-only SSH key, whose authorized_keys line forces this script (DEPLOY.md, section 5).
# GitHub Actions builds owner-web/ and sends the build as a gzip tar on stdin; the command it sends,
# which arrives in SSH_ORIGINAL_COMMAND, is the full commit SHA the build was made from:
#
#   tar -C owner-web/dist -czf - . | ssh -i <upload key> ubuntu@bottlemap.o-r.kr <commit sha>
#
# Each upload goes to a new directory $OWNER_WEB_ROOT/releases/<sha>-<time>, even for a SHA uploaded before,
# and $OWNER_WEB_ROOT/current is switched to it in one step, so a page load sees either the old build or the
# new one and the directory current points at is never removed. OWNER_WEB_DIR in backend/.env points at
# current; the API looks the directory up on every request, so no restart is needed.
set -euo pipefail

OWNER_WEB_ROOT="${OWNER_WEB_ROOT:-$HOME/bottlemap-owner-web}"
# A build is well under 1 MB today; refuse anything far larger instead of filling the disk. The unpacked
# limit stops a small archive that expands to gigabytes (a gzip bomb), and the timeout one that is slow to.
MAX_ARCHIVE_BYTES=$((50 * 1024 * 1024))
MAX_UNPACKED_BYTES=$((200 * 1024 * 1024))
UNPACK_SECONDS=60
KEEP_RELEASES=3

fail() {
	echo "owner-web-upload: $*" >&2
	exit 1
}

sha="${SSH_ORIGINAL_COMMAND:-${1:-}}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "expected the full commit SHA as the command (got '${sha}')"

releases="$OWNER_WEB_ROOT/releases"
mkdir -p "$releases"
work="$(mktemp -d "$releases/.upload.XXXXXX")"
trap 'rm -rf "$work"' EXIT

archive="$work/build.tar.gz"
head -c "$((MAX_ARCHIVE_BYTES + 1))" > "$archive"
[ "$(stat -c %s "$archive")" -le "$MAX_ARCHIVE_BYTES" ] || fail "the archive is larger than $MAX_ARCHIVE_BYTES bytes"

# Decompress once, reading at most one byte past the limit, so the tar steps below work on a file whose
# size is known; the files it holds cannot add up to more than the tar itself.
tarball="$work/build.tar"
set +o pipefail
timeout "$UNPACK_SECONDS" gzip -dc "$archive" 2>/dev/null | head -c "$((MAX_UNPACKED_BYTES + 1))" > "$tarball"
statuses=("${PIPESTATUS[@]}")
set -o pipefail
[ "$(stat -c %s "$tarball")" -le "$MAX_UNPACKED_BYTES" ] || fail "the archive unpacks to more than $MAX_UNPACKED_BYTES bytes"
[ "${statuses[0]}" -ne 124 ] || fail "unpacking took longer than $UNPACK_SECONDS seconds"
[ "${statuses[0]}" -eq 0 ] || fail "not a gzip archive"

# Only plain files and directories with relative paths that stay inside the build: no links, devices,
# absolute paths or "..", which could write outside the release directory.
tar -tvf "$tarball" > "$work/listing" || fail "not a tar archive"
if grep -qv '^[-d]' "$work/listing"; then
	fail "the archive holds something other than files and directories"
fi
tar -tf "$tarball" > "$work/names"
if grep -qE '^/|(^|/)\.\.(/|$)' "$work/names"; then
	fail "the archive holds a path outside the build"
fi

build="$work/build"
mkdir "$build"
tar -xf "$tarball" -C "$build" --no-same-owner --no-same-permissions
[ -f "$build/index.html" ] || fail "the archive has no index.html at its top"
chmod -R u=rwX,go=rX "$build"

# A new name for every upload: uploading the SHA that is already served (a re-run) must not remove the
# directory current points at while requests read from it.
name="$sha-$(date -u +%Y%m%dT%H%M%SZ)-$$"
release="$releases/$name"
mv -T "$build" "$release"

# Switch in one rename: a symlink made next to current replaces it atomically.
ln -sfn "releases/$name" "$OWNER_WEB_ROOT/current.new"
mv -T "$OWNER_WEB_ROOT/current.new" "$OWNER_WEB_ROOT/current"
echo "==> owner web: serving $sha ($name)"

# Keep the newest few releases, so a rollback by hand is one symlink away.
find "$releases" -mindepth 1 -maxdepth 1 -type d ! -name '.upload.*' -printf '%T@ %p\n' |
	sort -rn | tail -n +"$((KEEP_RELEASES + 1))" | cut -d' ' -f2- |
	while IFS= read -r old; do
		[ "$(readlink -f "$old")" = "$(readlink -f "$release")" ] || rm -rf "$old"
	done
