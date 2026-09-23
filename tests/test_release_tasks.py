from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTaskTests(unittest.TestCase):
    def test_cataloged_tasks_are_complete(self):
        catalog = json.loads((ROOT / "configs/catalog.json").read_text(encoding="utf-8"))
        entries = catalog.get("entries")
        self.assertIsInstance(entries, list)
        self.assertTrue(entries)
        self.assertEqual(len(entries), len({row["id"] for row in entries}))
        for entry in entries:
            contract_path = ROOT / entry["path"]
            self.assertTrue(contract_path.is_file(), contract_path)
            contract = json.loads(contract_path.read_text(encoding="utf-8"))

            self.assertEqual(contract.get("benchmark"), "constraint-shift-math")
            self.assertEqual(contract.get("family_id"), entry["id"])
            self.assertIsInstance(contract.get("generator"), dict)
            self.assertTrue(contract["generator"].get("id"))
            self.assertTrue(contract["generator"].get("version"))
            self.assertIsInstance(contract.get("submission_contract"), dict)
            self.assertTrue(contract["submission_contract"])
            instances = contract.get("instances")
            self.assertIsInstance(instances, list)
            self.assertGreaterEqual(len(instances), 3)
            identities = [row.get("id") for row in instances]
            self.assertEqual(len(identities), len(set(identities)))


    def test_protocol_is_frozen(self):
        protocol = json.loads((ROOT / "configs/protocol.json").read_text(encoding="utf-8"))
        self.assertIs(protocol.get("frozen"), True)
        self.assertIn("math", protocol)
        self.assertNotIn("coding", protocol)

    def test_packaged_protocol_is_identical_to_frozen_protocol(self):
        self.assertEqual(
            (ROOT / "src/mathbench/protocol.json").read_bytes(),
            (ROOT / "configs/protocol.json").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
