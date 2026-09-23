from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from benchcore import load_json, load_jsonl
from mathbench import grade_family
from mathbench.generators_constraints import BUILDERS


ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "tasks/math"
REFERENCE_ROOT = ROOT / "examples/private/math-reference"
PROTOCOL = load_json(ROOT / "configs/protocol.json")


def _input_edit_distance(left, right) -> int:
    if "edges" in left and "edges" in right:
        stable = int(left.get("vertices") != right.get("vertices")) + int(left.get("k") != right.get("k"))
        left_edges = {tuple(sorted(edge)) for edge in left["edges"]}
        right_edges = {tuple(sorted(edge)) for edge in right["edges"]}
        return stable + len(left_edges ^ right_edges)
    sequence_key = "numbers" if "numbers" in left else "weights"
    stable_keys = (set(left) | set(right)) - {sequence_key}
    stable = sum(left.get(key) != right.get(key) for key in stable_keys)
    first, second = left[sequence_key], right[sequence_key]
    return stable + sum(a != b for a, b in zip(first, second)) + abs(len(first) - len(second))


class ConstraintFamilyTests(unittest.TestCase):
    def private_rows(self, family_id: str):
        path = REFERENCE_ROOT / f"{family_id}.jsonl"
        if not path.is_file():
            self.skipTest("operator-only reference submissions are intentionally absent")
        return load_jsonl(path)

    def test_catalog_has_ten_four_item_families_and_four_validators(self):
        paths = sorted(TASK_ROOT.glob("*/family.json"))
        families = [load_json(path) for path in paths]
        self.assertEqual(len(families), 10)
        self.assertEqual(sum(len(family["instances"]) for family in families), 40)
        self.assertTrue(all(len(family["instances"]) == 4 for family in families))
        validators = {instance["validator"] for family in families for instance in family["instances"]}
        self.assertEqual(
            validators,
            {"bipartite_matching_v1", "subset_sum_v1", "graph_coloring_v1", "bin_packing_v1"},
        )

    def test_fixed_generators_match_checked_in_tasks_and_cross_one_edit_boundaries(self):
        for builder in BUILDERS.values():
            generated = builder()
            checked_in = load_json(TASK_ROOT / generated["family_id"] / "family.json")
            self.assertEqual(generated, checked_in)
            a, b, c, d = generated["instances"]
            self.assertEqual(_input_edit_distance(a["input"], b["input"]), 1)
            self.assertEqual(_input_edit_distance(b["input"], c["input"]), 1)
            self.assertEqual(c["input"], d["input"])
            self.assertNotEqual(c["goal"], d["goal"])

    def test_all_private_references_score_100(self):
        if not REFERENCE_ROOT.is_dir():
            self.skipTest("operator-only reference submissions are intentionally absent")
        self.assertTrue((REFERENCE_ROOT / "README.md").is_file())
        for builder in BUILDERS.values():
            family = builder()
            reference = REFERENCE_ROOT / f"{family['family_id']}.jsonl"
            self.assertTrue(reference.is_file(), reference)
            result = grade_family(family, load_jsonl(reference), PROTOCOL)
            self.assertEqual(result["score"], 100.0, family["family_id"])
            self.assertTrue(result["all_correct"])

    def test_subset_sum_rejects_forged_short_certificates_and_duplicate_indices(self):
        family = BUILDERS["pair-pivot"]()
        rows = self.private_rows("subset-pair-pivot-001")
        forged = deepcopy(rows)
        forged[2]["certificate"]["divisor"] = 4
        forged_result = grade_family(family, forged, PROTOCOL)["results"][2]
        self.assertFalse(forged_result["correct"])
        self.assertTrue(forged_result["schema_compliant"])

        unexpected_answer = deepcopy(rows)
        unexpected_answer[2]["answer"] = {"indices": []}
        answer_result = grade_family(family, unexpected_answer, PROTOCOL)["results"][2]
        self.assertFalse(answer_result["correct"])
        self.assertFalse(answer_result["schema_compliant"])

        duplicate = deepcopy(rows)
        duplicate[0]["answer"]["indices"] = [0, 0, 3]
        self.assertFalse(grade_family(family, duplicate, PROTOCOL)["results"][0]["correct"])

        superincreasing = BUILDERS["superincreasing-gap"]()
        super_rows = self.private_rows("subset-superincreasing-gap-001")
        wrong_remainder = deepcopy(super_rows)
        wrong_remainder[2]["certificate"]["remainder"] = 0
        self.assertFalse(grade_family(superincreasing, wrong_remainder, PROTOCOL)["results"][2]["correct"])

    def test_coloring_rejects_incomplete_coloring_and_nonedge_clique(self):
        family = BUILDERS["clique-completion"]()
        rows = self.private_rows("coloring-clique-completion-001")
        incomplete = deepcopy(rows)
        incomplete[0]["answer"]["coloring"].pop("d")
        self.assertFalse(grade_family(family, incomplete, PROTOCOL)["results"][0]["correct"])
        nonclique = deepcopy(rows)
        nonclique[2]["certificate"]["vertices"] = ["a", "b", "c", "ghost"]
        self.assertFalse(grade_family(family, nonclique, PROTOCOL)["results"][2]["correct"])

    def test_packing_rejects_duplicate_item_and_weak_lower_bound(self):
        family = BUILDERS["total-capacity"]()
        rows = self.private_rows("packing-total-capacity-001")
        duplicate = deepcopy(rows)
        duplicate[0]["answer"]["bins"][0].append(duplicate[0]["answer"]["bins"][0][0])
        self.assertFalse(grade_family(family, duplicate, PROTOCOL)["results"][0]["correct"])

        incompatibility = BUILDERS["incompatibility"]()
        rows = self.private_rows("packing-incompatibility-001")
        weak = deepcopy(rows)
        weak[2]["certificate"]["indices"] = [0, 1]
        self.assertFalse(grade_family(incompatibility, weak, PROTOCOL)["results"][2]["correct"])


if __name__ == "__main__":
    unittest.main()
