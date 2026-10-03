"""M2 journal tests: INV-15 (WAL, one file across the day change, broken tail), modes, lock, redaction."""
from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from agent import journal as J
from agent.contracts import Paths
from agent.journal import GENESIS, Journal, JournalError

DAY1 = time.mktime((2026, 10, 3, 12, 0, 0, 0, 0, -1))
DAY2 = time.mktime((2026, 10, 4, 9, 0, 0, 0, 0, -1))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t18-journal-")
        self.paths = Paths.at(self.tmp)
        self.paths.lock.parent.mkdir(parents=True, exist_ok=True)
        self.paths.lock.write_text(json.dumps({"pid": os.getpid(), "argv": ["run"]}), encoding="utf-8")
        self.now = DAY1

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def clock(self):
        return self.now

    def open(self, mode="dry", writer=True):
        return Journal(self.paths.journal, mode=mode, writer=writer, clock=self.clock)

    def send_intent(self, j, iid, ikind, args, tick=10):
        j.write("intent", id=iid, tactic="rastro", intent_kind=ikind, args=args, reason="r",
                expected_effect="e", prediction={"neg_lo": 3}, tick=tick)


class TestWriteAndChain(Base):
    def test_rows_header_chain_and_seq(self):
        j = self.open()
        self.assertEqual(j.write("tick", tick=5, cash=100), 1)
        self.assertEqual(j.write("alarm", what="x"), 2)
        rows = list(j.rows())
        self.assertEqual([r["seq"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["prev"], GENESIS)
        self.assertEqual(rows[0]["tick"], 5)
        self.assertNotIn("tick", rows[1])
        self.assertEqual(rows[0]["day"], "2026-10-03")
        self.assertEqual(rows[0]["mode"], "dry")
        raw = self.paths.journal.read_bytes().split(b"\n")[0]
        import hashlib
        self.assertEqual(rows[1]["prev"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(j.verify_chain())
        self.assertEqual([r["kind"] for r in j.rows({"alarm"})], ["alarm"])

    def test_fsync_only_for_fsync_kinds(self):
        j = self.open()
        with mock.patch.object(J.os, "fsync") as fs:
            j.write("tick", tick=1)
            self.assertEqual(fs.call_count, 0)
            self.send_intent(j, "a1", "cancel", {"offer_id": 1, "ref": None})
            self.assertEqual(fs.call_count, 1)
            j.write("result", id="a1", status="ok", code=None, response={})
            self.assertEqual(fs.call_count, 2)
        for k in ("intent", "result", "unknown", "reconciled", "accepted_unsettled", "stop", "cmd", "baseline"):
            self.assertIn(k, Journal.FSYNC)

    def test_reserved_and_bad_fields(self):
        j = self.open()
        for bad in ({"seq": 3}, {"prev": "x"}, {"ts": 1}, {"mode": "live"}):
            with self.assertRaises(JournalError):
                j.write("tick", **bad)
        with self.assertRaises(JournalError):
            j.write("Bad Kind")
        j.write("tick", mode="dry")          # same mode is fine
        self.assertTrue(j.verify_chain())

    def test_redaction(self):
        os.environ["BAZAAR_KEY"] = "tk-supersecretvalue123"
        try:
            j = self.open()
            j.write("error", detail="failed with tk-supersecretvalue123 in header", api_key="zzz",
                    nested={"token": "abc", "ok": "bk_abcdefghij"})
        finally:
            os.environ.pop("BAZAAR_KEY", None)
        text = self.paths.journal.read_text(encoding="utf-8")
        self.assertNotIn("supersecret", text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("bk_abcdefghij", text)
        self.assertNotIn('"token"', text)

    def test_sets_and_tuples_serialize(self):
        j = self.open()
        j.write("unknown", id="u1", domains={"offer:2", "ref:RET-01"}, error="net")
        row = list(j.rows({"unknown"}))[0]
        self.assertEqual(row["domains"], ["offer:2", "ref:RET-01"])

    def test_write_failure_raises_and_sticks(self):
        j = self.open()
        with mock.patch("builtins.open", side_effect=OSError("disk full")):
            with self.assertRaises(JournalError):
                j.write("intent", id="x")
        with self.assertRaises(JournalError):
            j.write("tick")


class TestModesAndLock(Base):
    def test_test_rows_refuse_live(self):
        j = self.open(mode="test")
        j.write("tick", tick=1)
        with self.assertRaises(JournalError):
            self.open(mode="live")
        with self.assertRaises(JournalError):
            self.open(mode="live", writer=False)
        self.open(mode="dry")                 # dry on a test journal is allowed

    def test_live_rows_refuse_test(self):
        j = self.open(mode="live")
        j.write("tick", tick=1)
        with self.assertRaises(JournalError):
            self.open(mode="test")
        j2 = self.open(mode="dry")
        j2.write("tick", tick=2)
        self.assertEqual([r["mode"] for r in j2.rows()], ["live", "dry"])

    def test_bad_mode(self):
        with self.assertRaises(JournalError):
            self.open(mode="prod")

    def test_writer_needs_lock(self):
        self.paths.lock.unlink()
        with self.assertRaises(JournalError):
            self.open()
        self.paths.lock.write_text(json.dumps({"pid": os.getpid() + 1}), encoding="utf-8")
        with self.assertRaises(JournalError):
            self.open()
        self.paths.lock.write_text(f"{os.getpid()} python3 bazaar.py run", encoding="utf-8")
        self.open()
        self.paths.lock.write_text("", encoding="utf-8")       # no pid and nobody holds it
        with self.assertRaises(JournalError):
            self.open()

    def test_held_lock_without_pid_is_accepted(self):
        self.paths.lock.write_text("", encoding="utf-8")
        with self.paths.lock.open("a+") as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            j = self.open()                    # held by this process through another handle
            j.write("tick", tick=1)
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except ImportError:
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def test_reader_needs_no_lock_and_cannot_write(self):
        self.open().write("tick", tick=1)
        self.paths.lock.unlink()
        r = self.open(writer=False)
        self.assertEqual(len(list(r.rows())), 1)
        with self.assertRaises(JournalError):
            r.write("tick")


class TestDayChange(Base):
    def test_one_file_across_days_keeps_own_objects(self):
        j = self.open(mode="live")
        self.send_intent(j, "i1", "list_offer", {"side": "sell", "ref": "MAL-01", "asset_id": 55, "price": 9,
                                                 "expires_ticks": 20, "closer": False, "want_ref": None})
        j.write("result", id="i1", status="ok", code=None, response={"offer_id": 900})
        self.send_intent(j, "i2", "open_thread", {"dealer": "abuela", "side": "buy", "ref": "RET-03",
                                                  "asset_ids": (), "limit": 12})
        j.write("result", id="i2", status="ok", code=None, response={"thread": {"id": 77}})
        self.send_intent(j, "i3", "say", {"thread_id": 77, "ref": "RET-03", "price": 5, "template": "t",
                                          "variant": 0})
        j.write("result", id="i3", status="ok", code=None, response={"id": 4321})
        self.send_intent(j, "i4", "duel_say", {"duel_id": 12, "price": 40, "days": None, "template": "t",
                                               "variant": 0}, tick=33)
        j.write("result", id="i4", status="ok", code=None, response={})
        self.send_intent(j, "i5", "accept", {"offer_id": 2500, "source": "team", "ref": "RET-01", "side": "buy",
                                             "price": 10, "thread_id": None, "give_asset": None,
                                             "fingerprint": "f", "resupply": False, "venue": "rastro"})
        j.write("result", id="i5", status="ok", code=None, response={})
        del j
        # restart on Sunday: same file, new rows carry the new day
        self.now = DAY2
        j = self.open(mode="live")
        j.write("tick", tick=300)
        self.send_intent(j, "i6", "list_offer", {"side": "bid", "ref": "CHA-02", "asset_id": None, "price": 20,
                                                 "expires_ticks": 40, "closer": False, "want_ref": None})
        j.write("reconciled", id="i6", landed=True, evidence={"offer": {"id": 901}})
        days = {r["day"] for r in j.rows()}
        self.assertEqual(days, {"2026-10-03", "2026-10-04"})
        self.assertEqual(list(self.paths.run_dir.glob("*.jsonl")), [self.paths.journal])
        own = j.own_objects({"offers": {"2503": 0.0, "2504": 0.0}, "dealer_threads": [5],
                             "thread_msgs": [1], "duel_msgs": [[149, 3, 50, 2]], "accepts": []})
        self.assertEqual(own["offers"], {900, 901, 2503, 2504})
        self.assertEqual(own["dealer_threads"], {77, 5})
        self.assertEqual(own["thread_msgs"], {4321, 1})
        self.assertEqual(own["duel_msgs"], {(12, 33, 40), (149, 3, 50)})
        self.assertEqual(own["accepts"], {2500})
        self.assertTrue(j.verify_chain())
        seqs = [r["seq"] for r in j.rows()]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))

    def test_explicit_own_field(self):
        j = self.open()
        j.write("reconciled", id="z", landed=True, evidence={}, own={"offers": [5], "duel_msgs": [[1, 2, 3]]})
        own = j.own_objects({})
        self.assertEqual(own["offers"], {5})
        self.assertEqual(own["duel_msgs"], {(1, 2, 3)})


class TestPendingAndIdempotency(Base):
    def test_intent_without_result_is_pending_and_frozen(self):
        j = self.open(mode="live")
        self.send_intent(j, "c1", "cancel", {"offer_id": 2463, "ref": "LAT-09"})
        # crash here: no result. Restart.
        j = self.open(mode="live")
        self.assertEqual([p["id"] for p in j.pending()], ["c1"])
        self.assertEqual(j.result_for("c1")["kind"], "intent")       # G05 must never re-send it
        self.assertEqual(j.unknown_domains(), {"offer:2463", "ref:LAT-09"})
        j.write("reconciled", id="c1", landed=True, evidence={"status": "cancelled"})
        self.assertEqual(j.pending(), [])
        self.assertEqual(j.unknown_domains(), set())
        self.assertEqual(j.result_for("c1")["kind"], "reconciled")

    def test_unknown_outcome(self):
        j = self.open(mode="live")
        self.send_intent(j, "u1", "say", {"thread_id": 8, "ref": "RET-02", "price": 4, "template": "t",
                                          "variant": 1})
        j.write("unknown", id="u1", domains=["thread:8", "ref:RET-02"], error="timeout")
        self.assertEqual(j.unknown_domains(), {"thread:8", "ref:RET-02"})
        self.assertEqual([p["pending"] for p in j.pending()], ["unknown"])
        self.assertEqual(j.result_for("u1")["kind"], "unknown")
        j.write("reconciled", id="u1", landed=False, evidence={})
        self.assertEqual(j.unknown_domains(), set())
        self.assertEqual(j.pending(), [])

    def test_unknown_without_domains_uses_intent_args(self):
        j = self.open(mode="live")
        self.send_intent(j, "u2", "open_pack", {"asset_id": 31})
        j.write("unknown", id="u2", error="5xx")
        self.assertEqual(j.unknown_domains(), {"asset:31"})

    def test_accepted_unsettled_until_reconciled_or_settled(self):
        j = self.open(mode="live")
        for iid, oid in (("a1", 10), ("a2", 11)):
            self.send_intent(j, iid, "accept", {"offer_id": oid, "source": "team", "ref": "RET-01", "side": "buy",
                                                "price": 10, "thread_id": None, "give_asset": None,
                                                "fingerprint": "f", "resupply": False, "venue": "rastro"})
            j.write("result", id=iid, status="ok", code=None, response={})
            j.write("accepted_unsettled", id=iid, offer_id=oid, ref="RET-01", price=10, until_tick=12)
        self.assertEqual(sorted(p["id"] for p in j.pending()), ["a1", "a2"])
        self.assertEqual({p["pending"] for p in j.pending()}, {"accepted_unsettled"})
        j.write("settlement", ids=["a1"], tick=11, cash_delta=-10, assets_in=[1], assets_out=[])
        j.write("reconciled", id="a2", landed=False, evidence={})
        self.assertEqual(j.pending(), [])
        self.assertEqual(j.result_for("a1")["status"], "ok")
        self.assertIsNone(j.result_for("nope"))

    def test_would_and_refused_count_as_results(self):
        j = self.open()
        j.write("would", id="w1", tactic="rastro", intent_kind="accept", code="would", detail="", prediction={})
        j.write("refused", id="r1", tactic="rastro", intent_kind="accept", code="G12", detail="", prediction={})
        self.assertEqual(j.result_for("w1")["kind"], "would")
        self.assertEqual(j.result_for("r1")["code"], "G12")
        self.assertEqual(j.pending(), [])

    def test_reader_sees_writer_rows_and_ignores_partial_line(self):
        w = self.open(mode="live")
        r = self.open(mode="live", writer=False)
        self.send_intent(w, "x1", "cancel", {"offer_id": 3, "ref": None})
        self.assertEqual([p["id"] for p in r.pending()], ["x1"])
        w.write("result", id="x1", status="ok", code=None, response={})
        with open(self.paths.journal, "ab") as f:
            f.write(b'{"seq":99,"kind":"inte')          # a write in flight
        self.assertEqual(r.pending(), [])
        self.assertTrue(r.verify_chain())


class TestBrokenTail(Base):
    def _journal_with_torn_intent(self, newline=False):
        j = self.open(mode="live")
        j.write("tick", tick=1)
        self.send_intent(j, "ok1", "cancel", {"offer_id": 1, "ref": None})
        j.write("result", id="ok1", status="ok", code=None, response={})
        good = self.paths.journal.read_bytes()
        torn = (b'{"seq":4,"ts":1,"tick":2,"day":"2026-10-03","mode":"live","kind":"intent","prev":"ab",'
                b'"id":"deadbeef00112233","tactic":"rastro","intent_kind":"accept","args":{"offer_id":2600,'
                b'"source":"team","ref":"RET-04","si')
        with open(self.paths.journal, "ab") as f:
            f.write(torn + (b"\n" if newline else b""))
        return good, torn

    def test_broken_last_line_goes_to_corrupt_and_chain_is_valid(self):
        good, torn = self._journal_with_torn_intent()
        j = self.open(mode="live")
        self.assertTrue(j.verify_chain())
        corrupt = self.paths.run_dir / "journal.corrupt"
        self.assertTrue(corrupt.exists())
        rec = json.loads(corrupt.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(base64.b64decode(rec["b64"]), torn)
        self.assertEqual(rec["offset"], len(good))
        rows = list(j.rows())
        self.assertEqual(rows[-1]["kind"], "truncated")
        self.assertEqual(rows[-1]["seq"], 4)
        import hashlib
        last_valid = good.rstrip(b"\n").split(b"\n")[-1]
        self.assertEqual(rows[-1]["prev"], hashlib.sha256(last_valid).hexdigest())
        self.assertTrue(self.paths.journal.read_bytes().startswith(good))
        # the intent that might have been stays pending and its domains frozen
        self.assertEqual(rows[-1]["maybe_intent"], "deadbeef00112233")
        self.assertIn("truncated", [p["pending"] for p in j.pending()])
        self.assertEqual(j.unknown_domains(), {"offer:2600", "ref:RET-04"})
        self.assertIsNotNone(j.result_for("deadbeef00112233"))
        j.write("reconciled", id="deadbeef00112233", landed=False, evidence={})
        self.assertEqual(j.pending(), [])
        self.assertEqual(j.unknown_domains(), set())
        self.assertEqual(j.write("tick", tick=3), 6)
        self.assertTrue(j.verify_chain())

    def test_broken_last_line_with_newline(self):
        self._journal_with_torn_intent(newline=True)
        j = self.open(mode="live")
        self.assertTrue(j.verify_chain())
        self.assertEqual(list(j.rows())[-1]["kind"], "truncated")

    def test_reader_does_not_recover(self):
        self._journal_with_torn_intent()
        r = self.open(mode="live", writer=False)
        self.assertFalse((self.paths.run_dir / "journal.corrupt").exists())
        self.assertEqual(len(list(r.rows())), 3)

    def test_valid_last_line_missing_newline_is_completed(self):
        j = self.open()
        j.write("tick", tick=1)
        j.write("tick", tick=2)
        data = self.paths.journal.read_bytes()
        self.paths.journal.write_bytes(data[:-1])
        j = self.open()
        self.assertFalse((self.paths.run_dir / "journal.corrupt").exists())
        self.assertEqual(j.write("tick", tick=3), 3)
        self.assertTrue(j.verify_chain())

    def test_tampered_middle_line_is_fatal(self):
        j = self.open()
        for t in range(4):
            j.write("tick", tick=t)
        lines = self.paths.journal.read_bytes().split(b"\n")
        lines[1] = lines[1].replace(b'"tick":1', b'"tick":7')
        self.paths.journal.write_bytes(b"\n".join(lines))
        with self.assertRaises(JournalError):
            self.open()
        self.assertFalse(self.open(writer=False).verify_chain())

    def test_writer_verify_rejects_partial_tail(self):
        j = self.open()
        j.write("tick", tick=1)
        with open(self.paths.journal, "ab") as f:
            f.write(b'{"seq":2')
        self.assertFalse(j.verify_chain())


class TestLegacyLog(unittest.TestCase):
    def test_log_still_writes(self):
        tmp = tempfile.mkdtemp(prefix="t18-log-")
        try:
            with mock.patch.object(J, "LOG_DIR", tmp):
                J.log("deals", ref="RET-01", price=3)
            row = json.loads((Path(tmp) / "deals.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["ref"], "RET-01")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
