#!/usr/bin/env bash
# Exchanges the OAuth client's secret (client_credentials grant) for a short-lived
# access token, and writes ZENDESK_OAUTH_TOKEN / ZENDESK_SUBDOMAIN to .oauth-token.env
# for zcli to pick up (see auth.js: ZENDESK_OAUTH_TOKEN takes priority over
# ZENDESK_EMAIL/ZENDESK_API_TOKEN). Never prints the secret or the token to stdout.
#
# Usage: ./scripts/get_zendesk_oauth_token.sh
#        source .oauth-token.env
set -euo pipefail

cd "$(dirname "$0")/.."

SUBDOMAIN="${ZENDESK_SUBDOMAIN:-ibm-38381}"
CLIENT_ID="${ZENDESK_OAUTH_CLIENT_ID:-testing-oauth-client}"
SECRET_FILE=".oauth-client-secret"
OUT_FILE=".oauth-token.env"

if [ ! -f "$SECRET_FILE" ]; then
  echo "Missing $SECRET_FILE -- put the client secret there (nothing else in the file)." >&2
  exit 1
fi

CLIENT_SECRET="$(tr -d '[:space:]' < "$SECRET_FILE")"

RESPONSE="$(curl -sS -X POST "https://${SUBDOMAIN}.zendesk.com/oauth/tokens" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c '
import json, sys
print(json.dumps({
    "grant_type": "client_credentials",
    "client_id": sys.argv[1],
    "client_secret": sys.argv[2],
    "scope": "read write",
}))
' "$CLIENT_ID" "$CLIENT_SECRET")")"

TOKEN="$(echo "$RESPONSE" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if 'access_token' not in data:
    print('ERROR: ' + json.dumps(data), file=sys.stderr)
    sys.exit(1)
print(data['access_token'])
")"

umask 177
{
  echo "export ZENDESK_SUBDOMAIN=${SUBDOMAIN}"
  echo "export ZENDESK_OAUTH_TOKEN=${TOKEN}"
} > "$OUT_FILE"

echo "Wrote $OUT_FILE (mode 600). Run: source $OUT_FILE"
