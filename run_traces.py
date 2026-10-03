"""Team trace viewer: what the agents are doing, live, from logs/*.jsonl. No game calls, no models, no cost.

    python3 run_traces.py                                   # http://127.0.0.1:8019, only this machine
    TRACES_PASSWORD=... python3 run_traces.py --host 0.0.0.0  # the team on the same network, Basic auth
    python3 run_traces.py --check                           # print the reconciliation report and exit (1 = descuadre)

Run it on the machine of the single executor, next to its logs. The page polls /state.json every 3 s.
The same read model feeds the RAG memory (agent/trace.py), so the viewer and the memory never disagree.
Opening it to other machines without TRACES_PASSWORD is refused: the logs hold our private limits.
"""
import argparse, base64, hmac, http.server, json, os, sys, threading, time  # noqa: E401

from agent import trace
from agent.journal import LOG_DIR
from harness import outcomes
from harness.retrieval import import_feed

CACHE_S = 2
_lock, _cache = threading.Lock(), {'at': 0.0, 'body': b''}


def state(log_dir):
    events, bad = trace.read(log_dir)
    summaries = trace.threads(events)
    feed = [c for c in import_feed(trace.read_feed(os.path.join(log_dir, 'feed.jsonl')), 'feed')[0]]
    ours = trace.team_cases(summaries)
    measured, outcome_report = outcomes.outcome_cases(*outcomes.load(log_dir))
    memory = trace.merge(feed, ours + measured)
    executor = trace.executor_status(log_dir, events)
    if executor is not None:
        executor['outcomes_indexed'] = outcome_report['indexed']
    reconciliation = trace.reconcile(summaries, feed)
    contradiction = (bad > 0 or not reconciliation['ok'] or outcome_report['chain_valid'] is False
                     or (executor is not None and not executor['journal_valid']))
    compared = reconciliation['in_feed']
    health = ('contradictory' if contradiction else 'no_data' if not events
              else 'consistent' if compared and not reconciliation['missing_in_feed'] else 'unverified')
    return {'generated': time.time(), 'bad_lines': bad, 'events_total': len(events),
            'executor': executor, 'outcomes': outcome_report,
            'observability': {'status': health, 'compared_threads': compared,
                              'executor_present': executor is not None,
                              'meaning': 'Consistency is not proof of ledger settlement or a running process.'},
            'events': events[-300:][::-1], 'threads': summaries[::-1][:200],
            'reconcile': reconciliation,
            'memory': {'cases': len(memory), 'team_cases': len(ours), 'measured_cases': len(measured),
                       'feed_cases': len(feed),
                       'ids_unique': len({c.id for c in memory}) == len(memory)}}


def _body(log_dir):
    with _lock:
        source = os.path.realpath(log_dir)
        if _cache.get('source') != source or time.time() - _cache['at'] >= CACHE_S or not _cache['body']:
            _cache['body'] = json.dumps(state(log_dir), ensure_ascii=False).encode('utf-8')
            _cache['at'] = time.time()
            _cache['source'] = source
        return _cache['body']


def make_handler(log_dir, password):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _authorized(self):
            if not password:
                return True
            got = self.headers.get('Authorization', '')
            try:
                if not got.startswith('Basic '):
                    return False
                user, separator, pwd = base64.b64decode(got[len('Basic '):], validate=True).partition(b':')
            except Exception:
                return False
            return bool(separator) and hmac.compare_digest(pwd, password.encode('utf-8'))

        def _send(self, code, body, kind, extra=None):
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._authorized():
                self._send(401, b'Contrasena del equipo', 'text/plain; charset=utf-8',
                           {'WWW-Authenticate': 'Basic realm="Team 18 traces", charset="UTF-8"'})
                return
            path = self.path.split('?')[0]
            try:
                if path == '/state.json':
                    self._send(200, _body(log_dir), 'application/json')
                elif path in ('/', '/index.html'):
                    self._send(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
                else:
                    self._send(404, b'not found', 'text/plain')
            except Exception as e:  # a broken log must not take the viewer down
                self._send(500, json.dumps({'error': repr(e)}).encode('utf-8'), 'application/json')

        def log_message(self, *args):
            pass
    return Handler


def serve(host, port, log_dir, password):
    if host not in ('127.0.0.1', 'localhost', '::1') and not password:
        raise SystemExit('Para abrirlo a otras máquinas define TRACES_PASSWORD: los logs contienen nuestros límites.')
    return http.server.ThreadingHTTPServer((host, port), make_handler(log_dir, password))


PAGE = r"""<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trazas equipo 18</title>
<style>
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--line:#e7e5e4;--ok:#15803d;--bad:#b91c1c;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--mut:#a8a29e;--line:#44403c;--ok:#4ade80;--bad:#f87171;--card:#292524}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
h1{font-size:18px;margin:0 0 4px}h2{font-size:15px;margin:20px 0 8px}
.mut{color:var(--mut)}.ok{color:var(--ok)}.bad{color:var(--bad)}
.tiles{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.tile b{display:block;font-size:18px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:var(--card)}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap}
td.wide{white-space:normal;min-width:240px}code{font-size:12px}
</style>
<h1>Trazas de los agentes · equipo 18</h1>
<div class="mut" id="when">cargando…</div>
<div class="tiles" id="tiles"></div>
<div id="rec"></div>
<div id="executor" class="mut"></div>
<h2>Conversaciones</h2><div class="wrap"><table><thead><tr><th>Dealer</th><th>Hilo</th><th>Lado</th><th>Carta</th><th>Ancla/Límite</th><th>Nuestras ofertas</th><th>Suyas</th><th>Estado</th><th>Precio</th><th>Motivo</th></tr></thead><tbody id="th"></tbody></table></div>
<h2>Eventos recientes</h2><div class="wrap"><table><thead><tr><th>Hora</th><th>Stream</th><th>Tick</th><th>Evento</th><th>Detalle</th></tr></thead><tbody id="ev"></tbody></table></div>
<script>
const $=id=>document.getElementById(id);
function row(cells){const tr=document.createElement('tr');for(const [v,cls] of cells){const td=document.createElement('td');td.textContent=v==null?'':String(v);if(cls)td.className=cls;tr.appendChild(td)}return tr}
function hhmm(ts){return ts?new Date(ts*1000).toLocaleTimeString():''}
function detail(e){const o={...e};for(const k of ['id','stream','ts','tick','event'])delete o[k];return JSON.stringify(o)}
async function tick(){
  try{
    const r=await fetch('state.json',{cache:'no-store'});const s=await r.json();if(s.error)throw new Error(s.error);
    $('when').textContent='Actualizado '+hhmm(s.generated)+' · '+s.events_total+' eventos · líneas ilegibles: '+s.bad_lines;
    const x=s.executor;
    $('executor').textContent=x?'Ejecutor v2 · modo '+x.mode+' · tick '+(x.tick??'?')+' · tácticas '+x.armed.join(', ')+' · pendientes '+(x.pending??'?')+' · cadena '+(x.journal_valid?'válida':'sin verificar')+' · STOP '+x.stop+' · último evento '+hhmm(x.last_ts)+'. Los resultados HTTP no confirman liquidación ni alimentan aún la memoria de desenlaces.':'Sin diario del ejecutor v2 en esta carpeta.';
    const c=s.reconcile,m=s.memory;
    $('tiles').replaceChildren(...[['Conversaciones',c.journal_threads],['Abiertas',c.open],['Terminadas',c.ended],['En el feed',c.in_feed],['Casos RAG',m.cases],['Desenlaces medidos',m.measured_cases]].map(([k,v])=>{const d=document.createElement('div');d.className='tile';d.innerHTML='<b></b><span class="mut"></span>';d.firstChild.textContent=v;d.lastChild.textContent=k;return d}));
    const p=document.createElement('div');const bad=[...c.dealer_mismatch,...c.price_not_in_feed,...c.side_mismatch];
    const health=s.observability.status;
    p.className=health==='consistent'&&m.ids_unique?'ok':health==='contradictory'||!m.ids_unique?'bad':'mut';
    p.textContent=health==='no_data'?'Sin registros: no se puede evaluar la memoria.':health==='unverified'?'Hay registros, pero falta evidencia comparable para verificar la memoria.':health==='consistent'&&m.ids_unique?'✔ Hilos comparados sin contradicciones. Esto no prueba una liquidación.':'✖ Datos contradictorios o diario incompleto. Hilos: '+bad.join(', ')+(m.ids_unique?'':' · IDs duplicados en memoria');
    $('rec').replaceChildren(p);
    $('th').replaceChildren(...s.threads.map(t=>row([[t.dealer],[t.thread],[t.side],[t.item],[(t.anchor??'?')+' → '+(t.limit??'?')],[t.ours.join(' · ')],[t.hers.join(' · ')],[t.status,t.status==='deal'?'ok':t.status==='open'?'':'mut'],[t.price],[t.reason,'wide']])));
    $('ev').replaceChildren(...s.events.map(e=>row([[hhmm(e.ts)],[e.stream],[e.tick],[e.event,e.event==='error'||e.event==='bug'?'bad':''],[detail(e),'wide']])));
  }catch(err){$('when').textContent='Sin datos nuevos: '+err.message}
}
tick();setInterval(tick,3000);
</script></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8019)
    ap.add_argument('--logs', default=LOG_DIR)
    ap.add_argument('--check', action='store_true', help='print the reconciliation report and exit')
    ap.add_argument('--require-executor', action='store_true', help='with --check, require a valid v2 journal with a tick')
    a = ap.parse_args()
    if a.check:
        s = state(a.logs)
        print(json.dumps({'bad_lines': s['bad_lines'], 'reconcile': s['reconcile'], 'memory': s['memory'],
                          'outcomes': s['outcomes'], 'executor': s['executor'], 'observability': s['observability']},
                         ensure_ascii=False, indent=2))
        valid = (s['events_total'] > 0 and s['bad_lines'] == 0
                 and (s['executor'] is None or s['executor']['journal_valid']))
        if a.require_executor:
            valid = valid and s['executor'] is not None and s['executor']['tick'] is not None
        sys.exit(0 if valid and s['reconcile']['ok'] and s['memory']['ids_unique'] else 1)
    server = serve(a.host, a.port, a.logs, os.environ.get('TRACES_PASSWORD', ''))
    print(f'Trazas en http://{a.host}:{a.port} (logs: {a.logs}; Ctrl+C para parar)', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
