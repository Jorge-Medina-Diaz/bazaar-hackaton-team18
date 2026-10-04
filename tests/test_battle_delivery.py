import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from prepare_battle_delivery import package_files, summary


class DeliveryTests(unittest.TestCase):
    def test_package_is_allowlisted_and_omits_private_and_operational_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dest=root/"out"
            (root/"mini_campo_batalla.py").write_text("# reviewable code\n")
            (root/".env").write_text("PRIVATE-KEY")
            hashes=package_files(root,dest,("mini_campo_batalla.py",))
            with zipfile.ZipFile(dest/"codigo-harness.zip") as z:
                self.assertEqual(z.namelist(),["mini_campo_batalla.py"])
            self.assertEqual(len(hashes["mini_campo_batalla.py"]),64)
            with self.assertRaises(ValueError):package_files(root,dest,(".env",))
            with self.assertRaises(ValueError):package_files(root,dest,("agent/world.py",))

    def test_summary_never_copies_raw_evidence_or_unknown_parameters(self):
        row={"selected_params":{"anchor":.6,"api_key":"PRIVATE-KEY"}}
        report={"simulation":{"roles":{"buyer":row,"seller":row}},
                "reference":{"roles":{r:{"recommendation":"retain_baseline"} for r in ("buyer","seller")}},
                "evidence":{"private_text":"PRIVATE-LOG"}}
        text=summary({"completed_batches":1,"private_state":"PRIVATE-STATE"},report)
        for secret in ("PRIVATE-KEY","PRIVATE-LOG","PRIVATE-STATE"):self.assertNotIn(secret,text)
