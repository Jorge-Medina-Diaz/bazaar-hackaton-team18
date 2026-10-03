"""Outcome adapter: measured v2 settlements -> RAG memory cases. Read-only and offline.

The only outcome label accepted is the Calibrator's `measure` row: a settlement it detected in the game
state, joined to the intent that caused it and judged against that intent's prediction by the change in
our points. An HTTP `ok`/`queued` result is never an outcome. Anything ambiguous, inherited, unattributed
or excluded by a round change stays out of the memory, and a broken chain indexes nothing.

Lives outside agent/ on purpose: it does not change the operator's code_hash.
"""
import json
import os

from agent.journal import Journal
from harness.retrieval import MemoryCase

SKIP_VERDICTS = frozenset({'excluded', 'unattributed', 'info', 'out_of_band'})
SETTLING = frozenset({'accept', 'list_offer', 'say'})


def journal_path(log_dir):
    for p in (os.path.join(log_dir, 'run', 'journal.jsonl'), os.path.join(log_dir, 'journal.jsonl')):
        if os.path.isfile(p):
            return p
    return None


def load(log_dir):
    """Rows of the v2 journal and whether its hash chain holds. Never repairs or writes."""
    path = journal_path(log_dir)
    if path is None:
        return [], None
    reader = Journal(path, mode='dry', writer=False)
    try:
        valid = reader.verify_chain()
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(-1, os.SEEK_END)
                valid = valid and handle.read(1) == b'\n'
        rows = list(reader.rows())
    except Exception:
        return [], False
    return rows, valid


def _side(intent, opens):
    """(side, dealer of the conversation we opened for this card, if any)."""
    a, k = intent.get('args') or {}, intent.get('intent_kind')
    # A shared ref is not a conversation identity. Only a successful open whose
    # response/reconciliation names this exact thread may supply its metadata.
    matches = [o for o in opens.get(a.get('thread_id'), [])
               if (o.get('tick') or 0) <= (intent.get('tick') or 0)
               and (o.get('args') or {}).get('ref') == a.get('ref')]
    opened = (matches[0].get('args') or {}) if len(matches) == 1 else None
    if k == 'accept':
        side = a.get('side') if a.get('side') in ('buy', 'sell') else 'unknown'
    elif k == 'list_offer':
        side = {'sell': 'sell', 'bid': 'buy'}.get(a.get('side'), 'unknown')
    else:
        side = (opened or {}).get('side') or 'unknown'
    return side, (opened or {}).get('dealer')


def outcome_cases(rows, valid=True):
    """(cases, report). One private case per unambiguous, harness-attributed, measured settlement."""
    report = {'chain_valid': valid, 'measures': 0, 'indexed': 0, 'skipped': {}}

    def skip(why):
        report['skipped'][why] = report['skipped'].get(why, 0) + 1

    if valid is False:
        report['refused'] = 'journal chain broken: nothing indexed'
        return [], report
    intents, done, opened_results = {}, set(), {}
    for r in rows:
        k = r.get('kind')
        if k == 'intent':
            intents[r.get('id')] = r
        elif (k == 'result' and r.get('status') in ('ok', 'sent')) or (k == 'reconciled' and r.get('landed')):
            done.add(r.get('id'))
            result = r.get('response') if k == 'result' else r.get('evidence')
            if isinstance(result, dict):
                tid = result.get('thread_id', result.get('id'))
                if type(tid) is int:
                    opened_results.setdefault(r.get('id'), set()).add(tid)
    opens = {}
    for iid, tids in opened_results.items():
        it = intents.get(iid)
        if it and it.get('intent_kind') == 'open_thread' and len(tids) == 1:
            for tid in tids:
                opens.setdefault(tid, []).append(it)
    cases, seen = [], set()
    for m in rows:
        if m.get('kind') != 'measure':
            continue
        report['measures'] += 1
        ids = m.get('ids') or []
        if m.get('verdict') in SKIP_VERDICTS or m.get('verdict') is None:
            skip('verdict:' + str(m.get('verdict')))
            continue
        if m.get('ambiguous') or len(ids) != 1:
            skip('ambiguous')  # several settlements share one points delta: no per-trade label
            continue
        if set(m.get('sources') or {}) != {'harness'}:
            skip('not_harness')
            continue
        it = intents.get(ids[0])
        if it is None or it.get('intent_kind') not in SETTLING:
            skip('no_settling_intent')
            continue
        if ids[0] not in done:
            skip('intent_not_sent')
            continue
        a, kind = it.get('args') or {}, it.get('intent_kind')
        side, opened_dealer = _side(it, opens)
        dealers = m.get('dealers') or []
        tid = a.get('thread_id')
        if kind == 'say' or tid is not None:
            if side not in ('buy', 'sell') or (opened_dealer and dealers and dealers != [opened_dealer]):
                skip('thread_identity_unverified')
                continue
            dealer = dealers[0] if len(dealers) == 1 else opened_dealer
            oid = f'thread-{tid}' if tid is not None else f'outcome-{ids[0]}'
        else:
            dealer = a.get('venue') or 'rastro'
            oid = f'outcome-{ids[0]}'
        if not dealer:
            skip('no_counterparty')
            continue
        if oid in seen:
            skip('duplicate')
            continue
        seen.add(oid)
        meas, pred = m.get('meas') or {}, m.get('pred') or {}
        body = json.dumps({'tactic': it.get('tactic'), 'action': kind, 'price': a.get('price'),
                           'price_source': 'intent_not_settlement_ledger',
                           'outcome_verification': 'calibrator_attributed',
                           'reason': it.get('reason'),
                           'predicted_neg': [pred.get('neg_lo'), pred.get('neg_hi')],
                           'measured_neg': meas.get('neg'), 'measured_ladder': meas.get('ladder'),
                           'verdict': m.get('verdict'), 'surprise': m.get('surprise'),
                           'opened_tick': m.get('opened')}, ensure_ascii=False)
        cases.append(MemoryCase(oid, dealer, side, a.get('ref') or 'unknown', 'settled', body,
                                f"journal#seq={m.get('seq')}", 'harness_measure', m.get('tick'),
                                visibility='local-team',
                                version='oct3-observations' if dealer in ('pilar', 'picaros') else 'oct2-observations',
                                round=m.get('round'),
                                regime='unknown'))
        report['indexed'] += 1
    return cases, report
