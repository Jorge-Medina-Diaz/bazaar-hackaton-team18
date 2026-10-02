"""Panel de inventario local: observa el laboratorio; no opera en el Bazaar."""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from inventory_panel import DEFAULT_STATE, demo_states
from live_monitor import make_monitor


HTML = Path(__file__).resolve().parent / "panel.html"


def make_handler(state_file, monitor=None):
    examples = demo_states()
    demo_index = 0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, content_type="application/json; charset=utf-8"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/demo":
                self.send(200, {**examples[demo_index], "demo_step": demo_index,
                                "demo_steps": len(examples)})
            elif path == "/api/state":
                if monitor is not None:
                    self.send(200, monitor.snapshot())
                    return
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    self.send(200, data)
                except FileNotFoundError:
                    self.send(404, {"error": "waiting", "message": "Esperando al laboratorio"})
                except (OSError, ValueError):
                    self.send(503, {"error": "unavailable", "message": "No se pudo leer el estado"})
            else:
                self.send(404, {"error": "not_found"})

        def do_POST(self):
            nonlocal demo_index
            # Solo cambia el ejemplo en memoria. Exige una llamada desde el panel local.
            if self.headers.get("X-Panel-Action") != "demo":
                self.send(403, {"error": "local_action_required"})
                return
            path = urlsplit(self.path).path
            if path == "/api/demo/next":
                demo_index = min(demo_index + 1, len(examples) - 1)
            elif path == "/api/demo/reset":
                demo_index = 0
            else:
                self.send(404, {"error": "not_found"})
                return
            self.send(200, {"ok": True})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--live", action="store_true", help="Consultar el Bazaar real cada 5 s, solo lectura")
    parser.add_argument("--key-file", type=Path, help="Archivo local de clave; nunca se envía al navegador")
    parser.add_argument("--url", default=os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Puerto fuera de rango")
    try:
        monitor = make_monitor(args.url, args.key_file) if args.live else None
    except (ValueError, OSError) as error:
        parser.error(str(error))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.state_file, monitor))
    if monitor:
        monitor.start()
    print(f"Panel: http://127.0.0.1:{args.port} · estado: {args.state_file}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if monitor:
            monitor.close()


if __name__ == "__main__":
    main()
