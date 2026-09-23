from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from benchcore import canonical_sha256, file_sha256, load_json, load_jsonl
from mathbench import grade_family
from mathbench.generators import build_matching_family


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "tasks/math/matching-shift-001/family.json"
PROTOCOL_PATH = ROOT / "configs/protocol.json"


class MathBenchTests(unittest.TestCase):
    def family(self):
        return load_json(FAMILY)

    def protocol(self):
        return load_json(PROTOCOL_PATH)

    def perfect_rows(self):
        return load_jsonl(ROOT / "examples/math-perfect.jsonl")

    def test_perfect_family_scores_100_and_binds_protocol(self):
        protocol = self.protocol()
        result = grade_family(self.family(), self.perfect_rows(), protocol)
        self.assertEqual(result["score"], 100.0)
        self.assertTrue(result["all_correct"])
        self.assertFalse(result["invalid_submission"])
        self.assertEqual(result["protocol_sha256"], canonical_sha256(protocol))

    def test_partial_family_loses_consistency_bonus(self):
        result = grade_family(
            self.family(),
            load_jsonl(ROOT / "examples/math-partial.jsonl"),
            self.protocol(),
        )
        self.assertEqual(result["score"], 52.5)
        self.assertFalse(result["all_correct"])
        self.assertEqual(sum(row["correct"] for row in result["results"]), 3)

    def test_protocol_is_the_actual_scoring_source(self):
        family = self.family()
        family.pop("scoring")
        protocol = self.protocol()
        protocol["math"]["item_pass_weight"] = 0.2
        protocol["math"]["family_strict_pass_weight"] = 0.8
        result = grade_family(
            family,
            load_jsonl(ROOT / "examples/math-partial.jsonl"),
            protocol,
        )
        self.assertEqual(result["score"], 15.0)
        self.assertEqual(
            result["scoring_weights"],
            {"item_pass_weight": 0.2, "family_strict_pass_weight": 0.8},
        )

    def test_family_scoring_declaration_must_match_protocol(self):
        protocol = self.protocol()
        protocol["math"]["item_pass_weight"] = 0.6
        protocol["math"]["family_strict_pass_weight"] = 0.4
        with self.assertRaisesRegex(ValueError, "differs from the frozen protocol"):
            grade_family(self.family(), self.perfect_rows(), protocol)

    def test_duplicate_and_unknown_ids_return_zero_receipts(self):
        row = self.perfect_rows()[0]
        duplicate = grade_family(self.family(), [row, row], self.protocol())
        self.assertTrue(duplicate["invalid_submission"])
        self.assertEqual(duplicate["score"], 0.0)
        self.assertIn("duplicate instance_id", duplicate["invalid_reason"])
        self.assertTrue(all(not result["correct"] for result in duplicate["results"]))

        unknown_row = deepcopy(row)
        unknown_row["instance_id"] = "not-in-this-family"
        unknown = grade_family(self.family(), [unknown_row], self.protocol())
        self.assertTrue(unknown["invalid_submission"])
        self.assertEqual(unknown["score"], 0.0)
        self.assertIn("unknown instance_id", unknown["invalid_reason"])

    def test_parser_error_can_be_sealed_as_zero_receipt(self):
        result = grade_family(
            self.family(),
            [],
            self.protocol(),
            submission_error="ValueError: duplicate JSON key",
            submission_sha256="0" * 64,
        )
        self.assertTrue(result["invalid_submission"])
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["submission_sha256"], "0" * 64)
        self.assertIn("submission parse error", result["invalid_reason"])

    def test_cli_turns_duplicate_keys_and_nonfinite_numbers_into_receipts(self):
        payloads = (
            '{"instance_id":"matching-shift-001-a","answer":{},"answer":{}}\n',
            '{"instance_id":"matching-shift-001-a","verdict":"feasible","answer":{"value":NaN},"certificate":{}}\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, payload in enumerate(payloads):
                with self.subTest(index=index):
                    submission = Path(directory) / f"bad-{index}.jsonl"
                    submission.write_text(payload, encoding="utf-8")
                    command = [
                        sys.executable,
                        "-m",
                        "mathbench.cli",
                        str(FAMILY),
                        str(submission),
                    ]
                    if index:
                        command.extend(["--protocol", str(PROTOCOL_PATH)])
                    completed = subprocess.run(
                        command,
                        cwd=ROOT,
                        env={
                            **dict(os.environ),
                            "PYTHONPATH": str(ROOT / "src"),
                            "PYTHONDONTWRITEBYTECODE": "1",
                        },
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    result = json.loads(completed.stdout)
                    self.assertTrue(result["invalid_submission"])
                    self.assertEqual(result["score"], 0.0)
                    self.assertEqual(result["submission_sha256"], file_sha256(submission))

    def test_task_configuration_errors_still_raise(self):
        family = self.family()
        family["instances"][0]["validator"] = "missing_validator"
        with self.assertRaisesRegex(ValueError, "Unknown validator"):
            grade_family(family, [], self.protocol(), submission_error="bad JSON")

    def test_evaluator_hash_covers_parser_cli_and_all_validators(self):
        result = grade_family(self.family(), self.perfect_rows(), self.protocol())
        source = ROOT / "src"
        expected = canonical_sha256(
            {
                "benchcore/__init__.py": file_sha256(source / "benchcore/__init__.py"),
                "benchcore/io.py": file_sha256(source / "benchcore/io.py"),
                "mathbench/__init__.py": file_sha256(source / "mathbench/__init__.py"),
                "mathbench/cli.py": file_sha256(source / "mathbench/cli.py"),
                "mathbench/grading.py": file_sha256(source / "mathbench/grading.py"),
                "mathbench/projection.py": file_sha256(source / "mathbench/projection.py"),
                "mathbench/validators.py": file_sha256(source / "mathbench/validators.py"),
                "mathbench/validators_bin_packing.py": file_sha256(
                    source / "mathbench/validators_bin_packing.py"
                ),
                "mathbench/validators_coloring.py": file_sha256(
                    source / "mathbench/validators_coloring.py"
                ),
                "mathbench/validators_subset_sum.py": file_sha256(
                    source / "mathbench/validators_subset_sum.py"
                ),
            }
        )
        self.assertEqual(result["evaluator_sha256"], expected)

    def test_duplicate_json_key_is_rejected_by_strict_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('{"instance_id":"a","instance_id":"b"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_jsonl(path)

    def test_generator_is_deterministic_and_crosses_boundary(self):
        first = build_matching_family(17, disclose_seed=True)
        second = build_matching_family(17, disclose_seed=True)
        different = build_matching_family(18, disclose_seed=True)
        self.assertEqual(first, second)
        self.assertNotEqual(first["instances"][0]["input"], different["instances"][0]["input"])
        self.assertEqual(first["generator"]["seed"], 17)
        self.assertIn("submission_contract", first)

        committed = deepcopy(first)
        digest = committed["generator"].pop("generation_payload_sha256")
        self.assertEqual(digest, canonical_sha256(committed))


if __name__ == "__main__":
    unittest.main()
