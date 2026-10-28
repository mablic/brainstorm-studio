#!/bin/bash
# Run directly: ./start.sh
set -Eeuo pipefail
# Repair missing Git Bash tools before invoking dirname/uname/awk/sleep.
# This changes only this launcher's environment, not the system PATH.
export PATH="/usr/bin:/bin:${PATH:-}"
if [[ -n "${MSYSTEM:-}" || "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
  export PATH="$PATH:/c/Windows/System32"
  if ! command -v node >/dev/null 2>&1 && [[ -x '/c/Program Files/nodejs/node.exe' ]]; then
    export PATH="$PATH:/c/Program Files/nodejs"
  fi
fi
hash -r
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

WINDOWS=false
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) WINDOWS=true; PYTHON='./.venv/Scripts/python.exe' ;;
  *) PYTHON='./.venv/bin/python' ;;
esac

[[ -f "$PYTHON" ]] || die 'Virtual environment missing. Follow README.md to install Python dependencies first.'
command -v node >/dev/null 2>&1 || die 'Node.js is missing from PATH.'
[[ -f frontend/node_modules/vite/bin/vite.js ]] || die 'Frontend dependencies missing. Run: cd frontend && npm install'
"$PYTHON" -c 'import uvicorn, fastapi, httpx' || die 'Run: python -m pip install -r requirements.txt (inside the virtual environment).'
"$PYTHON" -m backend.ollama_service || die 'Ollama could not be started. See the error above.'

# Pick available ports so an existing local server does not block startup.
read -r BACKEND_PORT FRONTEND_PORT < <("$PYTHON" - <<'PY'
import socket
import sys
import os

try:
    ports = [int(os.environ[name]) for name in ('BACKEND_PORT', 'FRONTEND_PORT')]
    if len(set(ports)) != 2 or any(not 1 <= port <= 65535 for port in ports):
        raise ValueError()
except ValueError:
    sys.exit('Choose two distinct ports between 1 and 65535.')
chosen = []
for start in ports:
    for port in range(start, min(start + 100, 65536)):
        if port in chosen:
            continue
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                continue
        chosen.append(port)
        break
    else:
        sys.exit(f'No available port near {start}.')
print(*chosen)
PY
)
FRONTEND_PORT="${FRONTEND_PORT%$'\r'}"
export BACKEND_PORT FRONTEND_PORT
export BRAINSTORM_BACKEND_PORT="$BACKEND_PORT"

BACKEND_PID=''
FRONTEND_PID=''
cleanup() {
  trap - EXIT INT TERM
  printf '\nStopping frontend and backend...\n'
  for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      if "$WINDOWS"; then
        # Use native PIDs and disable Git Bash's automatic argument conversion.
        native_pid="$(ps -p "$pid" 2>/dev/null | awk 'NR == 1 { for (i = 1; i <= NF; i++) if ($i == "WINPID") column = i; next } column { print $column }')"
        if [[ -n "$native_pid" ]]; then
          MSYS_NO_PATHCONV=1 taskkill.exe /PID "$native_pid" /T /F >/dev/null 2>&1 || true
        fi
      fi
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Starting BrainStorm...\n'
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
# Launch Vite directly so the tracked PID is the server, not an npm wrapper.
node frontend/node_modules/vite/bin/vite.js frontend --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort &
FRONTEND_PID=$!

"$PYTHON" - <<'PY'
import time
import urllib.request
import sys
import os

for url in (f"http://127.0.0.1:{os.environ['BACKEND_PORT']}/openapi.json", f"http://127.0.0.1:{os.environ['FRONTEND_PORT']}"):
    deadline = time.monotonic() + 30
    while True:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            sys.exit(f'Startup timed out: {url}. See server logs above.')
        time.sleep(0.3)
PY

printf '\nFrontend: http://127.0.0.1:%s\nBackend:  http://127.0.0.1:%s\nKeep Ollama running. Press Ctrl+C to stop both servers.\n\n' "$FRONTEND_PORT" "$BACKEND_PORT"

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
die 'A server exited. Stopping the other server.'
