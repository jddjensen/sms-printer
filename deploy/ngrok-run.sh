#!/usr/bin/env bash
# Launcher for ngrok. Reads NGROK_DOMAIN / NGROK_REGION from .env if set,
# so a paid reserved domain (stable URL across reboots) just works.
set -eu

DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$DIR/.env"
    set +a
fi

args=(http 5000 --log=stdout)

if [[ -n "${NGROK_DOMAIN:-}" ]]; then
    args+=(--domain="$NGROK_DOMAIN")
fi

if [[ -n "${NGROK_REGION:-}" ]]; then
    args+=(--region="$NGROK_REGION")
fi

exec /usr/local/bin/ngrok "${args[@]}"
