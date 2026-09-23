from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from benchcore import load_json
from mathbench import grade_family
from mathbench.generators import (
    build_matching_family,
    koenig_certificate,
    matching_reference_rows,
    maximum_matching,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = load_json(ROOT / "configs/protocol.json")


def _brute_force_matching_size(left, edges):
    adjacency = {vertex: [b for a, b in edges if a == vertex] for vertex in left}
    best = 0

    def search(index, used, count):
        nonlocal best
        if index == len(left):
            best = max(best, count)
            return
        search(index + 1, used, count)
        for target in adjacency[left[index]]:
            if target not in used:
                search(index + 1, used | {target}, count + 1)

    search(0, frozenset(), 0)
    return best


def _canonical_structure(family):
    data = family["instances"][0]["input"]
    left = {vertex: index for index, vertex in enumerate(data["left"])}
    right = {vertex: index for index, vertex in enumerate(data["right"])}
    return tuple(sorted((left[a], right[b]) for a, b in data["edges"]))


class MatchingSolverTests(unittest.TestCase):
    def test_hopcroft_karp_and_koenig_agree_with_brute_force(self):
        rng = random.Random(0)
        for _ in range(500):
            n = rng.randint(1, 6)
            left = [f"a{i}" for i in range(n)]
            right = [f"b{i}" for i in range(n)]
            density = rng.random()
            edges = [[a, b] for a in left for b in right if rng.random() < density]
            matching = maximum_matching(left, right, edges)
            cover_left, cover_right, hall = koenig_certificate(left, right, edges, matching)
            self.assertEqual(len(matching), _brute_force_matching_size(left, edges))
            self.assertTrue(all([a, b] in edges for a, b in matching.items()))
            self.assertTrue(all(a in cover_left or b in cover_right for a, b in edges))
            self.assertEqual(len(cover_left) + len(cover_right), len(matching))
            if len(matching) < n:
                self.assertLess(len({b for a, b in edges if a in set(hall)}), len(hall))
            else:
                self.assertEqual(hall, [])


class MatchingGeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_seed_sensitive(self):
        self.assertEqual(build_matching_family(5), build_matching_family(5))
        self.assertNotEqual(build_matching_family(5)["instances"], build_matching_family(6)["instances"])

    def test_structure_is_not_a_relabeled_fixed_template(self):
        structures = {_canonical_structure(build_matching_family(seed, size=12)) for seed in range(40)}
        self.assertEqual(len(structures), 40)

    def test_composition_varies_across_seeds(self):
        counts = Counter(build_matching_family(seed)["generator"]["composition"] for seed in range(100))
        self.assertEqual(set(counts), {"F,F,I,O", "F,I,I,O"})
        self.assertGreater(min(counts.values()), 20)

    def test_consecutive_instances_differ_by_one_edge_and_optimum_reuses_boundary(self):
        for seed in range(20):
            a, b, c, d = build_matching_family(seed)["instances"]
            for first, second in ((a, b), (b, c)):
                edges_first = {tuple(edge) for edge in first["input"]["edges"]}
                edges_second = {tuple(edge) for edge in second["input"]["edges"]}
                self.assertEqual(len(edges_first ^ edges_second), 1)
            self.assertEqual(c["input"], d["input"])

    def test_reference_certificates_grade_100_across_sizes(self):
        for size in (4, 5, 9, 32, 256):
            for seed in range(12):
                family = build_matching_family(seed, size=size)
                receipt = grade_family(family, matching_reference_rows(family), PROTOCOL)
                self.assertEqual(receipt["score"], 100.0, (size, seed, receipt["results"]))

    def test_all_feasible_guess_cannot_pass_the_family(self):
        family = build_matching_family(3)
        rows = matching_reference_rows(family)
        for row, instance in zip(rows, family["instances"]):
            if instance["goal"] == "classify_perfect_matching" and row["verdict"] == "infeasible":
                row.update(verdict="feasible", answer={"matching": []}, certificate={})
        self.assertFalse(grade_family(family, rows, PROTOCOL)["all_correct"])

    def test_size_and_seed_validation(self):
        for bad_size in (3, 2001, True):
            with self.assertRaises(ValueError):
                build_matching_family(1, size=bad_size)
        with self.assertRaises(ValueError):
            build_matching_family(-1)

    def test_generator_cli_accepts_size(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "family.json"
            environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
            completed = subprocess.run(
                [sys.executable, "-m", "mathbench.generator_cli", "--template", "matching",
                 "--seed", "23", "--size", "64", "--output", str(output)],
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            family = load_json(output)
            self.assertEqual(family["generator"]["size"], 64)
            self.assertNotIn("seed", family["generator"])
            self.assertTrue(all(len(row["input"]["left"]) == 64 for row in family["instances"]))


if __name__ == "__main__":
    unittest.main()
