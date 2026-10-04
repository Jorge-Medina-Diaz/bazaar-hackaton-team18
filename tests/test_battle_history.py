import copy
import unittest

from harness.battle_data import _read, FIXTURE
from harness.battle_history import historical_states, market_history


def deal(identifier,tick,team,price):
    return {"id":identifier,"tick":tick,"type":"settlement","payload":{
        "settlement":identifier,"persona":"abuela","price":price,"parties":["abuela",team],
        "items":[{"kind":"card","ref":"RET-01","rarity":"common","frm":"abuela","to":team}]}}


class HistoryTests(unittest.TestCase):
    def test_future_and_same_tick_trades_cannot_change_earlier_reference(self):
        prior=[deal(i,i,"t01" if i%2 else "t02",10) for i in range(1,6)]
        own=deal(6,6,"t18",8)
        a=market_history(prior+[own])["own_comparisons"]
        b=market_history(list(reversed(prior+[own,deal(7,6,"t03",999),deal(8,7,"t04",999)])))["own_comparisons"]
        self.assertEqual(a,b)
        self.assertEqual(a[0]["advantage_P"],2)

    def test_lots_duplicates_and_one_reference_team_cannot_inflate_evidence(self):
        prior=[deal(i,i,"t01",10) for i in range(1,6)]
        own=deal(6,6,"t18",8)
        lot=deal(7,7,"t02",20);lot["payload"]["items"]*=2
        report=market_history(prior+[own,copy.deepcopy(own),lot])
        self.assertEqual(report["own_comparisons"],[])
        self.assertEqual(report["eligible_single_card_settlements"],6)
        self.assertEqual(report["excluded"]["duplicate_settlement"],1)
        self.assertEqual(report["excluded"]["not_single_card"],1)

    def test_reference_balances_teams_and_requires_recent_observations(self):
        prior=[deal(i,i,"t01",10) for i in range(1,6)]+[deal(6,6,"t02",30)]
        self.assertEqual(market_history(prior+[deal(7,7,"t18",15)])["own_comparisons"][0]["advantage_P"],5)
        self.assertEqual(market_history(prior+[deal(7,500,"t18",15)])["own_comparisons"],[])

    def test_recorded_state_replay_is_safe_and_does_not_claim_counterfactual_wins(self):
        rows,_=_read(FIXTURE,"duels");original=copy.deepcopy(rows)
        r=historical_states(rows,{"precise":True,"punch":True,"punch_mode":"wait"})
        self.assertEqual(rows,original)
        self.assertGreater(r["states_tested"],100)
        self.assertEqual(r["failures"],0)
        self.assertFalse(r["counterfactual_wins_computed"])
