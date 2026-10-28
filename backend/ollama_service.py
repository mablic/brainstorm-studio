"""Local launcher preflight: reuse a daemon or start the installed Ollama."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

import httpx


def reachable(client, url):
    try:
        response = client.get(url + '/api/tags')
        response.raise_for_status()
        return isinstance(response.json().get('models'), list)
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def executable():
    configured = os.getenv('OLLAMA_BIN')
    if configured:
        return configured if Path(configured).is_file() else shutil.which(configured)
    located = shutil.which('ollama')
    if located:
        return located
    candidate = Path(os.getenv('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe'
    return str(candidate) if candidate.is_file() else None


def ensure_service():
    configured = os.getenv('OLLAMA_URL', '').rstrip('/')
    urls = [configured] if configured else ['http://127.0.0.1:11434', 'http://127.0.0.1:11435']
    with httpx.Client(timeout=2, trust_env=False) as client:
        for url in urls:
            if reachable(client, url):
                print('Ollama is running: ' + url, flush=True)
                return 0
        target = urls[0]
        parsed = urlsplit(target)
        if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            print('Error: configured Ollama is unavailable: ' + target, file=sys.stderr)
            return 1
        binary = executable()
        if not binary:
            print('Error: Ollama is not installed or not in PATH. Set OLLAMA_BIN to its executable.', file=sys.stderr)
            return 1
        log_path = Path(__file__).resolve().parents[1] / '.tmp' / 'ollama-serve.log'
        log_path.parent.mkdir(exist_ok=True)
        env = os.environ.copy()
        # Do not inherit OLLAMA_HOST=0.0.0.0 and expose a service on the LAN.
        env['OLLAMA_HOST'] = f'127.0.0.1:{parsed.port or 11434}'
        print('Starting installed Ollama: ' + binary, flush=True)
        with log_path.open('ab') as log:
            process = subprocess.Popen([binary, 'serve'], env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
        for _ in range(100):
            if reachable(client, target):
                print('Ollama is ready: ' + target, flush=True)
                return 0
            if process.poll() is not None:
                break
            time.sleep(.25)
        print(f'Error: Ollama did not become ready. See {log_path}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(ensure_service())
