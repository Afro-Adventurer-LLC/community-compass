#!/usr/bin/env bash
# Smoke test of a deployed environment.
#   smoke_test.sh <api-base-url> <frontend-url> <expected-git-sha>
#
# 1. GET  <api>/api/health  -> status ok, Bedrock retriever, generator configured, git_sha == expected
# 2. CORS preflight from the frontend origin is allowed
# 3. POST <api>/api/chat    -> HTTP 200 and a non-empty answer (one small Bedrock call)
# 4. GET  <frontend>/       -> 200 (401 is accepted: it means Basic Auth is on and the site is up)
set -euo pipefail

API="${1:?api base url}"
FRONT="${2:?frontend url}"
SHA="${3:?expected git sha}"
API="${API%/}"
FRONT="${FRONT%/}"
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

echo "1/4 health"
HEALTH="$(curl --fail --silent --show-error --max-time 30 "$API/api/health")"
jq -e '.status == "ok" and .mock == false and .knowledge_base == true and .llm_configured == true' <<<"$HEALTH" >/dev/null \
  || fail "health is not a real (non-mock) Bedrock deployment: $(jq -c '{status,mock,retriever,knowledge_base,llm_configured}' <<<"$HEALTH")"
GOT_SHA="$(jq -r '.git_sha' <<<"$HEALTH")"
[[ "$GOT_SHA" == "$SHA" ]] || fail "deployed git_sha ${GOT_SHA} != expected ${SHA}"
echo "   ok (git_sha matches)"

echo "2/4 CORS preflight"
ALLOW="$(curl --silent --show-error --max-time 30 -o /dev/null -D - -X OPTIONS "$API/api/chat" \
  -H "Origin: $FRONT" -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type' \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')"
[[ "$ALLOW" == "*" || "$ALLOW" == "$FRONT" ]] || fail "CORS does not allow origin ${FRONT} (got '${ALLOW}')"
echo "   ok"

echo "3/4 chat"
BODY="$(jq -nc '{question:"What does the All Builders Welcome grant cover?", role:"grantee", event_year:2026, include_alumni:true}')"
CODE="$(curl --silent --show-error --max-time 60 -o /tmp/smoke_chat.json -w '%{http_code}' \
  -X POST "$API/api/chat" -H 'Content-Type: application/json' -d "$BODY")"
[[ "$CODE" == "200" ]] || fail "chat returned HTTP ${CODE}"
jq -e '[.. | strings] | map(length) | add > 40' /tmp/smoke_chat.json >/dev/null || fail "chat answer is empty"
rm -f /tmp/smoke_chat.json
echo "   ok (answer returned; content is not graded here, see evals)"

echo "4/4 frontend"
CODE="$(curl --silent --show-error --max-time 30 -o /dev/null -w '%{http_code}' "$FRONT/")"
[[ "$CODE" == "200" || "$CODE" == "401" ]] || fail "frontend returned HTTP ${CODE}"
echo "   ok (HTTP ${CODE})"

echo "SMOKE OK"
