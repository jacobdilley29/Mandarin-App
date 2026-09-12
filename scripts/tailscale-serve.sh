#!/usr/bin/env bash
# Expose the local app to your phone over HTTPS, on your tailnet only.
#
# Tailscale Serve puts a real, trusted HTTPS certificate in front of the app at
# https://<machine>.<tailnet>.ts.net — which the Speak tab needs, since browsers
# only grant microphone access on a secure origin. Nothing is published to the
# public internet: only devices signed into your tailnet can reach it.
#
#   scripts/tailscale-serve.sh          # start (reads PORT from .env)
#   scripts/tailscale-serve.sh 3005     # start on an explicit port
#   scripts/tailscale-serve.sh --off    # stop serving
#   scripts/tailscale-serve.sh --status # show what's currently served

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

command -v tailscale >/dev/null 2>&1 || die \
  "tailscale is not installed or not on PATH.
  Install it from https://tailscale.com/download, then sign in with 'tailscale up'."

if ! tailscale status >/dev/null 2>&1; then
  die "tailscale is installed but this machine isn't connected. Run 'tailscale up' first."
fi

# Port: explicit argument > PORT in .env > 3002 (the app's default).
port_from_env() {
  [[ -f "$REPO_ROOT/.env" ]] || return 1
  grep -E '^[[:space:]]*PORT=' "$REPO_ROOT/.env" | tail -1 | cut -d= -f2 | tr -d '[:space:]'
}

case "${1:-}" in
  --off|off|down)
    info "Stopping Tailscale Serve…"
    tailscale serve --https=443 off
    echo "Stopped. The app is no longer reachable from your tailnet."
    exit 0
    ;;
  --status|status)
    tailscale serve status
    exit 0
    ;;
  "")
    PORT="$(port_from_env || echo 3002)"
    PORT="${PORT:-3002}"
    ;;
  *)
    PORT="$1"
    ;;
esac

if ! curl -fsS -o /dev/null --max-time 3 "http://127.0.0.1:${PORT}/api/health"; then
  printf '\033[33mwarning:\033[0m nothing is answering on http://127.0.0.1:%s — start the app first (make up).\n' "$PORT" >&2
  printf '          Serving anyway; it will start working once the app is up.\n\n' >&2
fi

info "Serving http://127.0.0.1:${PORT} over HTTPS on your tailnet…"
tailscale serve --bg "${PORT}"

echo
HOSTNAME_TS="$(tailscale status --json 2>/dev/null | grep -o '"DNSName"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4 | sed 's/\.$//')"
if [[ -n "${HOSTNAME_TS:-}" ]]; then
  echo "  Open this on your phone:  https://${HOSTNAME_TS}/"
else
  echo "  Open the https://…ts.net URL printed above on your phone."
fi
echo "  Then use the browser's 'Add to Home Screen' to install it as an app."
echo
echo "  Stop with: scripts/tailscale-serve.sh --off   (or: make tailscale-down)"
