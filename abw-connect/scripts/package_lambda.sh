#!/usr/bin/env bash
# Build a Lambda zip of the *committed* backend/app tree (git archive HEAD).
# Dirty worktree files are not packed — health git_sha is a deploy label, not
# proof that a previous zip matched git. Does not upload, does not print or
# require AWS credentials, and does not write account ids.
# See docs/AWS_DEPLOY.md for the env vars to set in Lambda.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/lambda-dist}"
ZIP_NAME="${2:-abw-connect-backend.zip}"
STAGE="$(mktemp -d)"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "package_lambda.sh: not a git work tree; refuse to pack a dirty copy" >&2
  exit 1
fi
SHA="$(git -C "$ROOT" rev-parse HEAD)"
if [[ ! "$SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "package_lambda.sh: could not resolve HEAD" >&2
  exit 1
fi

mkdir -p "$OUT_DIR" "$STAGE/app"
python3 -m pip install -q -r "$ROOT/backend/requirements.txt" -t "$STAGE"
# Exact committed tree only. Do not `cp` the worktree (that shipped a divergent
# generator.py under zip-stamped 257e811).
git -C "$ROOT" archive HEAD backend/app | tar -x -C "$STAGE"
if [[ -d "$STAGE/backend/app" ]]; then
  rm -rf "$STAGE/app"
  mv "$STAGE/backend/app" "$STAGE/app"
  rm -rf "$STAGE/backend"
fi

# Manifest: git blob id per packed app file. Fail if a file drifts from HEAD.
: > "$STAGE/app/_build_manifest.txt"
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  blob="$(git -C "$ROOT" rev-parse "HEAD:$rel")"
  packed="$STAGE/${rel#backend/}"
  got="$(git hash-object "$packed")"
  if [[ "$got" != "$blob" ]]; then
    echo "package_lambda.sh: $rel packed hash $got != git $blob" >&2
    exit 1
  fi
  printf '%s  %s\n' "$blob" "$rel" >> "$STAGE/app/_build_manifest.txt"
done < <(git -C "$ROOT" ls-files backend/app)

printf 'GIT_SHA = "%s"\n' "$SHA" > "$STAGE/app/_build_meta.py"

# Keep the bundle small: skip bytecode and tests.
find "$STAGE" -type d -name "__pycache__" -prune -exec rm -rf {} +
( cd "$STAGE" && zip -qr "$OUT_DIR/$ZIP_NAME" . )
echo "wrote $OUT_DIR/$ZIP_NAME ($(wc -c < "$OUT_DIR/$ZIP_NAME") bytes) sha=$SHA"
echo "do not commit this zip; set Lambda env from docs/AWS_DEPLOY.md"
