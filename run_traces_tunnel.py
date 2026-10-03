"""Authenticated trace viewer + temporary Cloudflare tunnel. Ctrl+C stops both.

python3 run_traces_tunnel.py --demo   # invented logs only, no game/model calls
python3 run_traces_tunnel.py          # actual logs from the executor; contains private data
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import threading

from agent.journal import LOG_DIR
import run_traces

ROOT = Path(__file__).resolve().parent


def password_from_file(path):
    """Create a private secret once; never put it in process arguments or output."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('El archivo de contraseña no puede ser un enlace simbólico.')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(secrets.token_urlsafe(32) + '\n')
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError('La contraseña debe estar en un archivo privado: chmod 600 ' + str(path))
    password = path.read_text(encoding='utf-8').strip()
    if len(password) < 24 or '\n' in password or '\r' in password:
        raise ValueError('Usa una contraseña aleatoria de al menos 24 caracteres.')
    return password


def demo_logs():
    """Only write our isolated demo directory. These prices and outcomes are invented."""
    directory = ROOT / 'runs' / 'traces-demo' / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    streams = {
        'abuela': [
            {'ts': 1, 'event': 'open', 'thread': 'demo-1', 'topic': {'buy': {'card': 'SAL-01'}},
             'anchor': 5, 'limit': 9, 'simulation': True},
            {'ts': 2, 'tick': 1, 'event': 'offer_sent', 'thread': 'demo-1', 'price': 5},
            {'ts': 3, 'tick': 2, 'event': 'accept_intent', 'thread': 'demo-1', 'price': 9},
            {'ts': 4, 'event': 'end', 'thread': 'demo-1', 'status': 'deal', 'price': 9,
             'reason': 'DEMO: compra simulada, no ocurrió en el juego'},
        ],
        'chato': [
            {'ts': 5, 'event': 'open', 'thread': 'demo-2', 'topic': {'buy': {'card': 'LAT-06'}},
             'anchor': 16, 'limit': 22, 'simulation': True},
            {'ts': 6, 'tick': 3, 'event': 'offer_sent', 'thread': 'demo-2', 'price': 16},
        ],
        'loop': [{'ts': 7, 'event': 'error', 'reason': 'DEMO: error inventado para verificar el visor',
                  'api_token': 'FAKE_SECRET_MUST_NOT_REACH_VIEWER'}],
        'feed': [
            {'id': 'demo-a', 'tick': 0, 'scope': 'public', 'type': 'thread.opened',
             'payload': {'thread': 'demo-1', 'with': 'abuela', 'topic': {'buy': {'card': 'SAL-01'}}}},
            {'id': 'demo-b', 'tick': 2, 'scope': 'public', 'type': 'thread.message',
             'payload': {'thread': 'demo-1', 'with': 'abuela', 'sender': 'abuela', 'text': 'DEMO: precio 9',
                         'offer': {'give': {'types': ['card:SAL-01']}, 'want': {'cash': 9}}}},
            {'id': 'demo-c', 'tick': 3, 'scope': 'public', 'type': 'thread.closed',
             'payload': {'thread': 'demo-1', 'with': 'abuela'}},
        ],
    }
    for stream, rows in streams.items():
        with (directory / (stream + '.jsonl')).open('w', encoding='utf-8') as f:
            f.writelines(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    return str(directory)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--demo', action='store_true', help='serve isolated invented logs only')
    ap.add_argument('--logs', help='executor logs; incompatible with --demo')
    ap.add_argument('--port', type=int, default=8019)
    ap.add_argument('--password-file', default=str(ROOT / 'runs' / 'traces.password'))
    args = ap.parse_args()
    if args.demo and args.logs:
        ap.error('--demo y --logs son incompatibles: la demo no debe leer logs reales.')
    executable = shutil.which('cloudflared')
    if not executable:
        ap.error('Falta cloudflared. En macOS: HOMEBREW_NO_AUTO_UPDATE=1 brew install cloudflared')
    try:
        password = password_from_file(args.password_file)
    except (OSError, ValueError) as e:
        ap.error(str(e))
    log_dir = demo_logs() if args.demo else args.logs or LOG_DIR
    server = run_traces.serve('127.0.0.1', args.port, log_dir, password)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'Visor autenticado: {origin}; contraseña en {args.password_file}', flush=True)
    print('SOLO SIMULACIÓN' if args.demo else 'Logs del ejecutor: acceso solo para el equipo', flush=True)
    process = None
    # A normal SIGTERM must also stop the child rather than leaving a public tunnel running.
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        process = subprocess.Popen([executable, 'tunnel', '--no-autoupdate', '--grace-period', '1s',
                                    '--metrics', '127.0.0.1:0', '--url', origin],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match:
                print('URL temporal: ' + match.group(), flush=True)
            elif 'ERR' in line:
                print('Cloudflare: error de conexión; comprueba red/configuración.', flush=True)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        server.shutdown()
        server.server_close()
        print('Visor y túnel detenidos.', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
