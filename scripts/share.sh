#!/usr/bin/env bash
#
# Put the game on the public internet for as long as this script runs.
#
# Starts the server locally, then opens a tunnel to it and prints an
# https:// address anyone in the world can open. No account, no port
# forwarding, nothing touching your router. The address is new every run
# and dies when you press Ctrl-C.
#
# Two providers are tried in turn, because "it printed an address" and
# "that address works" are not the same thing — a tunnel can connect
# happily and still never get a DNS record. Each one is held to actually
# serving the home page before it is handed over, and if it does not, the
# next is tried.
#
#   ./scripts/share.sh                    try each provider in turn
#   ./scripts/share.sh --via localhost.run   force one
#   PORT=5050 ./scripts/share.sh          if 5000 is taken
#
# For an address that stays put, deploy instead — see DEPLOY.md.

set -uo pipefail

PORT="${PORT:-5000}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WANTED="${2:-}"
[[ "${1:-}" == "--via" ]] || WANTED=""

SERVER_PID=""
TUNNEL_PID=""

cleanup() {
    [[ -n "$TUNNEL_PID" ]] && kill "$TUNNEL_PID" 2>/dev/null
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null
    return 0
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# The game itself
# ---------------------------------------------------------------------------

echo "Starting the game on port $PORT..."
( cd "$HERE/backend" && DEBUG=0 PORT="$PORT" python3 app.py ) >/tmp/hgs-server.log 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
    # -s not -sS: a refused connection here only means "not up yet", and
    # printing that once a second looks like something is wrong.
    curl -fs -o /dev/null "http://127.0.0.1:$PORT/" && break
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "The server exited. Last lines:" >&2
        tail -20 /tmp/hgs-server.log >&2
        exit 1
    fi
    sleep 0.5
done

# ---------------------------------------------------------------------------
# Tunnels
# ---------------------------------------------------------------------------

# name | how to check it is available | how to start it | how to spot the URL
tunnel_cmd() {
    case "$1" in
        cloudflared)
            echo "cloudflared tunnel --url http://127.0.0.1:$PORT" ;;
        localhost.run)
            # nokey@ skips the account; the host key options stop ssh
            # stopping to ask about a host it has never seen.
            echo "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -R 80:localhost:$PORT nokey@localhost.run" ;;
    esac
}

tunnel_pattern() {
    case "$1" in
        cloudflared)   echo 'https://[a-z0-9-]+\.trycloudflare\.com' ;;
        localhost.run) echo 'https://[a-z0-9.-]+\.lhr\.life' ;;
    esac
}

tunnel_available() {
    case "$1" in
        cloudflared)   command -v cloudflared >/dev/null 2>&1 ;;
        localhost.run) command -v ssh >/dev/null 2>&1 ;;
    esac
}

# Bring one up and return its address on stdout, or nothing.
try_tunnel() {
    local name="$1" log="/tmp/hgs-tunnel-$1.log" url=""
    : >"$log"

    # shellcheck disable=SC2086 - the command is built above, word split on purpose
    $(tunnel_cmd "$name") >"$log" 2>&1 &
    TUNNEL_PID=$!

    for _ in $(seq 1 40); do
        url="$(grep -oE "$(tunnel_pattern "$name")" "$log" 2>/dev/null | head -1)"
        [[ -n "$url" ]] && break
        kill -0 "$TUNNEL_PID" 2>/dev/null || break
        sleep 0.5
    done

    if [[ -z "$url" ]]; then
        echo "  $name never printed an address." >&2
        kill "$TUNNEL_PID" 2>/dev/null; TUNNEL_PID=""
        return 1
    fi

    # The address existing is not the address working. cloudflared in
    # particular prints one the moment it is assigned, while the DNS
    # record behind it is created separately and may never appear.
    echo "  $name gave $url - checking it answers..." >&2
    for _ in $(seq 1 30); do
        if curl -fs -o /dev/null --max-time 5 "$url/"; then
            echo "$url"
            return 0
        fi
        kill -0 "$TUNNEL_PID" 2>/dev/null || break
        sleep 2
    done

    echo "  $name's address never answered; trying the next one." >&2
    kill "$TUNNEL_PID" 2>/dev/null; TUNNEL_PID=""
    return 1
}

PROVIDERS=(cloudflared localhost.run)
[[ -n "$WANTED" ]] && PROVIDERS=("$WANTED")

echo "Opening a tunnel..."
PUBLIC=""
for name in "${PROVIDERS[@]}"; do
    if ! tunnel_available "$name"; then
        echo "  $name is not installed, skipping." >&2
        continue
    fi
    PUBLIC="$(try_tunnel "$name")" && break
    PUBLIC=""
done

if [[ -z "$PUBLIC" ]]; then
    cat >&2 <<'MSG'

No tunnel would come up. Both are free services, so the usual cause is
one of them having a bad day rather than anything here being wrong.

  - Retry; these often work on a second attempt.
  - cloudflared: brew install cloudflared
  - Or deploy for an address that stays put: see DEPLOY.md

Logs: /tmp/hgs-tunnel-*.log
MSG
    exit 1
fi

cat <<MSG

  Send your friends:  $PUBLIC

  They open it in a browser, one of you creates a room, and the rest
  join with the code. Ctrl-C here ends the game and kills the address.

MSG

# Either one dying should bring the whole thing down rather than leave
# half a game running. Polled rather than `wait -n`, which needs bash 4.3
# and macOS still ships 3.2.
while kill -0 "$SERVER_PID" 2>/dev/null && kill -0 "$TUNNEL_PID" 2>/dev/null; do
    sleep 1
done
