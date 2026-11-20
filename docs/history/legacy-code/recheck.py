"""Recheck offline de código y feed guardado. No llama al juego ni inicia agentes."""
raise SystemExit("ARCHIVED by M18: pre-harness script that could reach the game without the Gate. Use the harness: python3 bazaar.py (see CLAUDE.md).")  # M18 guard
import contextlib
import argparse
import importlib.util
import io
import hashlib
import json
import subprocess
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from negotiation_policy import decide_purchase

ROOT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def run(candidate=False):
    santi = git('rev-parse', 'origin/Santi')
    jorge = git('rev-parse', 'origin/feat/jorge')
    path = ROOT / 'agent/scorer.py' if candidate else ROOT.parent / 'bazaar-hackaton-team18-strategy/agent/scorer.py'
    spec = importlib.util.spec_from_file_location('review_scorer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = (ROOT / 'agent/haggle.py').read_text() if candidate else git('show', jorge + ':agent/haggle.py')
    source = source.replace('from bazaar_sdk import Bazaar', '').replace('from agent.journal import log', '')
    engine = {'Bazaar': object, 'log': lambda *args, **kwargs: None}
    exec(compile(source, jorge + ':agent/haggle.py', 'exec'), engine)

    card = {'id': 'SAL-01', 'set': 'SAL', 'book': 10, 'rarity': 'common'}
    snap = SimpleNamespace(cards={'SAL-01': card}, sets={'SAL': {'name': 'Fixture',
        'released': True, 'cards': [card]}}, my_offer_ids=set(), venues={}, boards={},
        clock={'tick': 0}, me={'id': 't18', 'cash': 100, 'assets': []})
    values = module.Values.__new__(module.Values)
    values.snap, values.mult = snap, {'SAL': 1.0}
    values.counts, values.copy_values = defaultdict(int), defaultdict(list)
    values.marginals, values.page_bonus = [1.0, 0.25, 0.1], 0.25
    scorer = module.Scorer.__new__(module.Scorer)
    scorer.snap, scorer.v = snap, values

    def offer(give, want):
        return {'id': 1, 'status': 'open', 'give': give, 'want': want}

    # Evitar bonus de cierre en esta prueba de duplicados.
    values.page_bonus = 0
    snap.boards = {'fixture': [offer({'assets': [{'id': 2, 'kind': 'card', 'ref': 'SAL-01'},
                                              {'id': 3, 'kind': 'card', 'ref': 'SAL-01'}]}, {})]}
    duplicates = scorer.board_offers()[0]['surplus']
    values.counts['SAL-01'], values.copy_values['SAL-01'] = 1, [10]
    snap.me['assets'] = [{'id': 1, 'kind': 'card', 'ref': 'SAL-01'}]
    snap.boards = {'fixture': [offer({'cash': 30}, {'types': ['card:SAL-01', 'card:SAL-01']})]}
    invalid_quantity = len(scorer.board_offers())
    values.page_bonus = 0.25
    complete_page = scorer.pages({'SAL-01': {'buy_at': 9, 'mv': 10}})[0]['net']

    own = {'id': 2, 'maker': 't18', 'to': 'abuela', 'status': 'settled',
           'give': {'cash': 9}, 'want': {'cash': 0, 'types': ['card:SAL-01']}}
    fake = SimpleNamespace(open_thread=lambda *a, **k: {'id': 1},
        thread=lambda *a: {'status': 'deal', 'messages': [{'offer': own}], 'standing_offers': []},
        me=lambda: {'id': 't18', 'cash': 100, 'open_threads': []}, clock=lambda: {'tick': 0})
    with contextlib.redirect_stdout(io.StringIO()):
        paid = engine['haggle'](fake, 'abuela', {'buy': {'card': 'SAL-01'}},
            anchor=5, limit=9, rounds=6, beta=1, lines=['{p}'])['price']

    probes = [
        {'case': 'dos copias recibidas', 'actual': duplicates, 'expected': 12.5,
         'source': 'agent/scorer.py:446', 'risk': 'Sobrevalora paquetes al repetir el mismo marginal.'},
        {'case': 'piden dos copias, tenemos una', 'actual': invalid_quantity, 'expected': 0,
         'source': 'agent/scorer.py:456', 'risk': 'Presenta una oferta que no podemos satisfacer.'},
        {'case': 'pagina ya completa', 'actual': complete_page, 'expected': 0,
         'source': 'agent/scorer.py:439', 'risk': 'Cuenta otra vez el bonus al valorar completar una página completa.'},
        {'case': 'dealer acepta nuestra propuesta de compra', 'actual': paid, 'expected': 9,
         'source': 'agent/haggle.py:44', 'risk': 'Lee el cash del lado equivocado de una oferta propia liquidada.'},
    ]
    for p in probes:
        p['mismatch'] = p['actual'] != p['expected']

    states = []
    for ask, maximum, last, k, final in [(12, 9, None, 0, False), (10, 9, 5, 1, False),
            (9, 9, 7, 2, False), (12, 9, 9, 6, False), (9, 9, 7, 2, True)]:
        ours = decide_purchase(ask, maximum, last_sent=last, final=final)
        nxt = engine['curve'](k, max(1, maximum * 3 // 5), maximum, 6, 1)
        if last is not None:
            nxt = max(last + 1, nxt)
        action = ('accept' if ask <= maximum and (ask <= nxt or final or k >= 6)
                  else 'close' if final or nxt > maximum else 'offer')
        states.append({'ask': ask, 'limit': maximum, 'last': last, 'final': final,
            'codex': {'action': ours.action, 'price': ours.price},
            'jorge': {'action': action, 'price': ask if action == 'accept' else nxt if action == 'offer' else None}})

    feed_path = ROOT / 'runs/recheck-feed.json'
    events = json.loads(feed_path.read_text())['events'] if feed_path.exists() else []
    rivals = []
    for team in ('t10', 't13', 't08', 't14'):
        fills = [e for e in events if e['type'] == 'settlement'
                 and team in e['payload'].get('parties', [])]
        rivals.append({'team': team, 'settlements': [{'event': e['id'], 'tick': e['tick'],
            'price': e['payload'].get('price'), 'dealer': e['payload'].get('persona'),
            'items': e['payload'].get('items')} for e in fills]})
    return {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'candidate': candidate,
        'revisions': {'santi': santi, 'jorge': jorge, 'codex': git('rev-parse', 'HEAD')},
        'source_hashes': {'scorer': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'haggle': hashlib.sha256(source.encode()).hexdigest()},
        'scorer_loaded_from': str(spec.origin),
        'scorer_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
            cwd=Path(spec.origin).parent.parent, text=True).strip(),
        'scope': 'Fixtures sintéticas y comparación de decisiones de precio; no torneo ni prueba de persuasión.',
        'probes': probes, 'decision_comparison': states, 'rivals': rivals,
        'feed_window': {'events': len(events), 'min_tick': min((e['tick'] for e in events), default=None),
                        'max_tick': max((e['tick'] for e in events), default=None)}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-public', action='store_true',
                        help='Actualizar feed, reloj y leaderboard con GET públicos, sin clave.')
    parser.add_argument('--candidate', action='store_true', help='Verificar los módulos corregidos de esta rama.')
    args = parser.parse_args()
    if args.refresh_public:
        (ROOT / 'runs').mkdir(exist_ok=True)
        for name, route in [('feed', 'feed?limit=1000'), ('clock', 'clock'), ('leaderboard', 'leaderboard')]:
            with urllib.request.urlopen('https://bazaar.causaprima.ai/api/' + route, timeout=15) as response:
                data = json.load(response)
            (ROOT / ('runs/recheck-' + name + '.json')).write_text(json.dumps(data, ensure_ascii=False))
    report = run(candidate=args.candidate)
    out = ROOT / 'runs'
    out.mkdir(exist_ok=True)
    path = out / ('recheck-candidate.json' if args.candidate else 'recheck.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (out / 'rechecks.jsonl').open('a') as stream:
        stream.write(json.dumps(report, ensure_ascii=False) + '\n')
    print(f"Recheck guardado: {path}")
    for probe in report['probes']:
        print(f"{'REVISAR' if probe['mismatch'] else 'OK'}: {probe['case']} "
              f"observado={probe['actual']} esperado={probe['expected']}")
    print(report['scope'])
    if args.candidate and any(p['mismatch'] for p in report['probes']):
        raise SystemExit(1)
