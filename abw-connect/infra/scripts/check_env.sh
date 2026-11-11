#!/usr/bin/env bash
# Safety check run by every deploy workflow before it touches AWS.
#   check_env.sh <staging|prod>   (run from the infra/ directory)
# Fails if the environment's tfvars would point at the hand-built live app (plain "abw-connect"
# prefix) or at the wrong environment's prefix.
set -euo pipefail

ENV_NAME="${1:?staging or prod}"
case "$ENV_NAME" in
  staging) WANT="abw-connect-staging" ;;
  prod) WANT="abw-connect-prod" ;;
  *) echo "unknown environment: $ENV_NAME" >&2; exit 1 ;;
esac

FILE="envs/${ENV_NAME}.tfvars"
PREFIX="$(sed -n 's/^[[:space:]]*name_prefix[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$FILE" | head -n 1)"
[[ -n "$PREFIX" ]] || { echo "check_env: no name_prefix in $FILE" >&2; exit 1; }
if [[ "$PREFIX" == "abw-connect" ]]; then
  echo "check_env: $FILE uses the live app's prefix. Refusing." >&2
  exit 1
fi
if [[ "$PREFIX" != "$WANT" ]]; then
  echo "check_env: $FILE has name_prefix '$PREFIX', expected '$WANT'. Refusing." >&2
  exit 1
fi
echo "check_env: ${ENV_NAME} -> prefix ${PREFIX} (not the live app)"
