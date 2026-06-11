#!/usr/bin/env zsh
set -euo pipefail

TOKEN_FILE="${GITHUB_TOKEN_FILE:-$HOME/.config/hotspot-research-suite/github_token}"

if [[ ! -f "$TOKEN_FILE" ]]; then
  cat >&2 <<EOF
GitHub token file not found: $TOKEN_FILE

Create it with:
  mkdir -p ~/.config/hotspot-research-suite
  cp /tmp/.gh_token ~/.config/hotspot-research-suite/github_token
  chmod 600 ~/.config/hotspot-research-suite/github_token
EOF
  exit 1
fi

TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
if [[ -z "$TOKEN" ]]; then
  echo "GitHub token file is empty: $TOKEN_FILE" >&2
  exit 1
fi

HEADER="$(printf 'x-access-token:%s' "$TOKEN" | base64)"
exec git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $HEADER" push "$@"
