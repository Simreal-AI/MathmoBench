from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from benchcore import canonical_sha256, load_json, load_jsonl
from mathbench.projection import (
    AGENT_INSTANCE_FIELDS,
    AGENT_VIEW_FIELDS,
    binding_maps,
    export_family_projection,
    project_family,
    translate_agent_submissions,
)
from mathbench.generators import build_matching_family


ROOT = Path(__file__).resolve().parents[1]
FAMILY_PATH = ROOT / "tasks/math/matching-shift-001/family.json"
FORBIDDEN_FIELDS = ("variant", "validator", "generator", "title", "track", "scoring", "reference")
FORBIDDEN_HINT = re.compile(
    r"\b(?:feasible|infeasible|feasibility|boundary|critical|non[-_\s]?critical)\b",
    re.IGNORECASE,
)


class MathProjectionTests(unittest.TestCase):
    def setUp(self):
        self.family = load_json(FAMILY_PATH)

    def test_projection_is_recursive_allowlist_without_answer_hints(self):
        projection, binding = project_family(self.family, seed=101)
        self.assertEqual(set(projection), AGENT_VIEW_FIELDS)
        self.assertTrue(all(set(row) == AGENT_INSTANCE_FIELDS for row in projection["instances"]))
        serialized = json.dumps(projection, ensure_ascii=False, sort_keys=True)
        lowered = serialized.casefold()
        for field in FORBIDDEN_FIELDS:
            self.assertNotIn(field, lowered)
        for row in projection["instances"]:
            public_task_content = json.dumps(
                {key: row[key] for key in ("goal", "statement", "input")},
                ensure_ascii=False,
                sort_keys=True,
            )
            self.assertIsNone(FORBIDDEN_HINT.search(public_task_content))
        self.assertNotIn(self.family["family_id"], serialized)
        for source in self.family["instances"]:
            self.assertNotIn(source["id"], serialized)
        for row in projection["instances"]:
            self.assertRegex(row["id"], r"^q_[0-9]{39}$")
            self.assertNotRegex(row["id"], r"(?:^|[-_])[abcd](?:$|[-_])")

        classify_prompts = {
            row["statement"]
            for row in projection["instances"]
            if row["goal"] == "classify_perfect_matching"
        }
        self.assertEqual(len(classify_prompts), 1)
        self.assertEqual(
            set(projection["goal_contracts"]),
            {"classify_perfect_matching", "maximum_matching"},
        )
        self.assertEqual(
            set(projection["goal_contracts"]["classify_perfect_matching"]["verdicts"]),
            {"feasible", "infeasible"},
        )
        self.assertEqual(binding["agent_projection_sha256"], canonical_sha256(projection))

    def test_every_checked_in_family_projects_through_the_same_whitelist(self):
        paths = sorted((ROOT / "tasks/math").glob("*/family.json"))
        self.assertEqual(len(paths), 10)
        for path in paths:
            family = load_json(path)
            projection, binding = project_family(family, salt=f"projection-test:{path.parent.name}")
            self.assertEqual(set(projection), AGENT_VIEW_FIELDS)
            self.assertTrue(all(set(row) == AGENT_INSTANCE_FIELDS for row in projection["instances"]))
            self.assertEqual(len(projection["instances"]), len(family["instances"]))
            self.assertEqual(binding["agent_projection_sha256"], canonical_sha256(projection))
            for row in projection["instances"]:
                self.assertIsNone(FORBIDDEN_HINT.search(row["statement"]))

    def test_subset_contract_distinguishes_positive_and_nonnegative_remainders(self):
        family = load_json(ROOT / "tasks/math/subset-superincreasing-gap-001/family.json")
        projection, _ = project_family(family, seed=9)
        classify = projection["goal_contracts"]["classify_exact_subset"]
        optimize = projection["goal_contracts"]["closest_subset"]
        classify_super = classify["verdicts"]["infeasible"]["certificate_one_of"][1]
        optimize_super = optimize["verdicts"]["optimal"]["certificate_one_of"][1]
        self.assertEqual(classify_super["type"], "superincreasing_greedy")
        self.assertEqual(classify_super["remainder"], "positive integer")
        self.assertEqual(optimize_super["remainder"], "nonnegative integer")

    def test_same_seed_writes_byte_equivalent_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_view, first_binding = root / "first-view.json", root / "first-binding.json"
            second_view, second_binding = root / "second-view.json", root / "second-binding.json"
            export_family_projection(self.family, first_view, first_binding, seed=101)
            export_family_projection(self.family, second_view, second_binding, seed=101)
            self.assertEqual(first_view.read_bytes(), second_view.read_bytes())
            self.assertEqual(first_binding.read_bytes(), second_binding.read_bytes())
            self.assertFalse(any(path.name.startswith(".") for path in root.iterdir()))

    def test_different_seed_changes_order_and_opaque_ids(self):
        first_projection, first_binding = project_family(self.family, seed=101)
        second_projection, second_binding = project_family(self.family, seed=102)
        first_order = [row["operator_instance_id"] for row in first_binding["instance_bindings"]]
        second_order = [row["operator_instance_id"] for row in second_binding["instance_bindings"]]
        self.assertNotEqual(first_order, second_order)
        first_ids = {row["id"] for row in first_projection["instances"]}
        second_ids = {row["id"] for row in second_projection["instances"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertNotEqual(first_projection["projection_id"], second_projection["projection_id"])

    def test_binding_round_trips_and_binds_both_payloads(self):
        projection, binding = project_family(self.family, salt="candidate-run-17")
        operator_to_agent, agent_to_operator = binding_maps(binding)
        self.assertEqual(set(operator_to_agent), {row["id"] for row in self.family["instances"]})
        self.assertEqual(set(agent_to_operator), {row["id"] for row in projection["instances"]})
        for operator_id, agent_id in operator_to_agent.items():
            self.assertEqual(agent_to_operator[agent_id], operator_id)

        core = dict(binding)
        digest = core.pop("binding_sha256")
        self.assertEqual(digest, canonical_sha256(core))
        self.assertEqual(binding["operator_family_sha256"], canonical_sha256(self.family))
        self.assertEqual(binding["agent_projection_sha256"], canonical_sha256(projection))
        self.assertNotIn("candidate-run-17", json.dumps(binding, sort_keys=True))

    def test_sensitive_nested_canaries_fail_closed(self):
        field_canary = deepcopy(self.family)
        field_canary["instances"][0]["input"]["validator_hint"] = "opaque"
        with self.assertRaisesRegex(ValueError, "forbidden public field"):
            project_family(field_canary, seed=1)

        word_canary = deepcopy(self.family)
        word_canary["instances"][0]["input"]["note"] = "critical"
        with self.assertRaisesRegex(ValueError, "answer-revealing term"):
            project_family(word_canary, seed=1)

    def test_submission_translation_validates_binding_and_preserves_candidate_faults(self):
        projection, binding = project_family(self.family, seed=101)
        rows = [
            {
                "instance_id": instance["id"],
                "verdict": "candidate-value",
                "answer": {},
                "certificate": {},
            }
            for instance in projection["instances"]
        ]
        translated = translate_agent_submissions(binding, self.family, rows)
        expected_order = [row["operator_instance_id"] for row in binding["instance_bindings"]]
        self.assertEqual([row["instance_id"] for row in translated], expected_order)
        self.assertEqual([row["instance_id"] for row in rows], [row["id"] for row in projection["instances"]])

        candidate_faults = deepcopy(rows[:2])
        candidate_faults[0]["instance_id"] = "matching-shift-001-a"
        candidate_faults[1]["instance_id"] = 7
        translated_faults = translate_agent_submissions(binding, self.family, candidate_faults)
        self.assertTrue(all(row["instance_id"].startswith("__unmapped_agent_instance_") for row in translated_faults))
        self.assertTrue(
            all(row["instance_id"] not in {instance["id"] for instance in self.family["instances"]} for row in translated_faults)
        )

        tampered = deepcopy(binding)
        tampered["agent_projection_sha256"] = "0" * 64
        core = dict(tampered)
        core.pop("binding_sha256")
        tampered["binding_sha256"] = canonical_sha256(core)
        with self.assertRaisesRegex(ValueError, "projection hash mismatch"):
            translate_agent_submissions(tampered, self.family, rows)

        wrong_family = deepcopy(self.family)
        wrong_family["instances"][0]["input"]["left"] = ["changed"]
        with self.assertRaisesRegex(ValueError, "operator family does not match binding"):
            translate_agent_submissions(binding, wrong_family, rows)

    def test_randomization_and_destination_validation(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            project_family(self.family)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            project_family(self.family, seed=1, salt="x")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "same.json"
            with self.assertRaisesRegex(ValueError, "distinct output paths"):
                export_family_projection(self.family, destination, destination, seed=1)

    def test_private_tracks_require_a_high_entropy_secret_salt(self):
        family = build_matching_family(18)
        with self.assertRaisesRegex(ValueError, "require --salt"):
            project_family(family, seed=1)
        with self.assertRaisesRegex(ValueError, "at least 32 bytes"):
            project_family(family, salt="too-short")
        projection, binding = project_family(family, salt="s" * 32)
        self.assertEqual(binding["randomization_kind"], "salt")
        self.assertEqual(len(projection["instances"]), 4)

    def test_cli_writes_agent_and_evaluator_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent_view, binding = root / "agent.json", root / "evaluator.json"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mathbench.projection_cli",
                    str(FAMILY_PATH),
                    "--agent-view",
                    str(agent_view),
                    "--binding",
                    str(binding),
                    "--seed",
                    "101",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            projected = load_json(agent_view)
            evaluator = load_json(binding)
            self.assertEqual(summary["projection_id"], projected["projection_id"])
            self.assertEqual(summary["projection_sha256"], canonical_sha256(projected))
            self.assertEqual(summary["binding_sha256"], evaluator["binding_sha256"])

    def test_grading_cli_round_trips_opaque_ids_and_binds_projection(self):
        projection, binding = project_family(self.family, seed=404)
        operator_to_agent, _ = binding_maps(binding)
        rows = load_jsonl(ROOT / "examples/math-perfect.jsonl")
        public_rows = []
        for row in rows:
            public_row = deepcopy(row)
            public_row["instance_id"] = operator_to_agent[row["instance_id"]]
            public_rows.append(public_row)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding_path = root / "binding.json"
            submission_path = root / "submission.jsonl"
            binding_path.write_text(
                json.dumps(binding, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            submission_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in public_rows),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mathbench.cli",
                    str(FAMILY_PATH),
                    str(submission_path),
                    "--binding",
                    str(binding_path),
                ],
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
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            receipt = json.loads(completed.stdout)
            self.assertEqual(receipt["score"], 100.0)
            self.assertEqual(receipt["agent_projection_sha256"], canonical_sha256(projection))
            self.assertEqual(receipt["agent_binding_sha256"], binding["binding_sha256"])

            public_rows[0]["instance_id"] = "q_000000000000000000000000000000000000000"
            submission_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in public_rows),
                encoding="utf-8",
            )
            rejected = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mathbench.cli",
                    str(FAMILY_PATH),
                    str(submission_path),
                    "--binding",
                    str(binding_path),
                ],
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
            self.assertEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
            rejected_receipt = json.loads(rejected.stdout)
            self.assertTrue(rejected_receipt["invalid_submission"])
            self.assertEqual(rejected_receipt["score"], 0.0)

    def test_checked_in_matching_classification_prompts_are_neutral_and_identical(self):
        statements = [row["statement"] for row in self.family["instances"][:3]]
        self.assertEqual(len(set(statements)), 1)
        self.assertIsNone(FORBIDDEN_HINT.search(statements[0]))


if __name__ == "__main__":
    unittest.main()
