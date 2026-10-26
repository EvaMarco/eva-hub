#!/usr/bin/env bash
# Sync from GitHub, build the page and serve it on http://localhost:8800
# Usage: scripts/serve.sh [port]   (--no-sync to reuse the last data)
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8800
SYNC=1
for arg in "$@"; do
  case "$arg" in
    --no-sync) SYNC=0 ;;
    *) PORT="$arg" ;;
  esac
done

[ "$SYNC" = 1 ] && python3 scripts/sync.py
python3 render.py
echo "Hub en http://localhost:$PORT (Ctrl+C para parar)"
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory site
