from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from schedule_training_cutoff import request_if_due, timestamp, run
import json


class CutoffTests(unittest.TestCase):
    def test_only_offline_sentinel_is_created_and_never_before_deadline(self):
        deadline = timestamp("2026-10-04T13:30:00+02:00")
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            self.assertFalse(request_if_due(out, deadline, deadline-timedelta(seconds=1)))
            self.assertEqual(list(out.iterdir()), [])
            self.assertTrue(request_if_due(out, deadline, deadline))
            self.assertEqual([p.name for p in out.iterdir()], ["STOP_TRAINING"])
            self.assertTrue(request_if_due(out, deadline, deadline+timedelta(seconds=1)))

    def test_missing_timezone_is_rejected(self):
        with self.assertRaises(ValueError):
            timestamp("2026-10-04T13:30:00")

    def test_completed_schedule_does_not_stop_a_new_trainer_on_next_login(self):
        deadline=timestamp("2026-10-04T13:30:00+02:00")
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);status=out/"entrenamiento";status.mkdir()
            (status/"cutoff.json").write_text(json.dumps({"deadline":deadline.isoformat(),
                                                        "requested_at":deadline.isoformat(),"phase":"prepared"}))
            run(out,deadline)
            self.assertFalse((out/"STOP_TRAINING").exists())
