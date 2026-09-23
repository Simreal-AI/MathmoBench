from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any


SCORING = {"correctness_weight": 70, "all_correct_bonus": 30}

SUBSET_CONTRACT = {
    "top_level_fields": ["instance_id", "verdict", "answer", "certificate"],
    "indexing": "zero_based",
    "classify_feasible": {"verdict": "feasible", "answer": {"indices": ["integer"]}, "certificate": {}},
    "classify_infeasible": {
        "verdict": "infeasible",
        "answer": {},
        "certificate_one_of": [
            {"type": "common_divisor", "divisor": "integer > 1 dividing every number"},
            {"type": "superincreasing_greedy", "remainder": "positive greedy remainder"},
        ],
    },
    "optimize": {
        "verdict": "optimal",
        "answer": {"indices": ["integer"], "distance": "nonnegative integer"},
        "certificate_one_of": [
            {"type": "common_divisor", "divisor": "integer > 1 dividing every number"},
            {"type": "superincreasing_greedy", "remainder": "nonnegative greedy remainder"},
        ],
    },
    "additional_fields": False,
}

COLORING_CONTRACT = {
    "top_level_fields": ["instance_id", "verdict", "answer", "certificate"],
    "classify_feasible": {"verdict": "feasible", "answer": {"coloring": {"vertex": "integer in 1..k"}}, "certificate": {}},
    "classify_infeasible": {
        "verdict": "infeasible",
        "answer": {},
        "certificate_one_of": [
            {"type": "clique", "vertices": ["vertex"]},
            {"type": "odd_cycle", "cycle": ["cyclically ordered vertex"]},
            {"type": "odd_wheel", "hub": "vertex", "rim": ["cyclically ordered vertex"]},
        ],
    },
    "optimize": {
        "verdict": "optimal",
        "answer": {"coloring": {"vertex": "integer"}, "colors_used": "positive integer"},
        "certificate": "one obstruction above whose lower bound equals colors_used",
    },
    "additional_fields": False,
}

PACKING_CONTRACT = {
    "top_level_fields": ["instance_id", "verdict", "answer", "certificate"],
    "indexing": "zero_based",
    "classify_feasible": {"verdict": "feasible", "answer": {"bins": [["item index"]]}, "certificate": {}},
    "classify_infeasible": {
        "verdict": "infeasible",
        "answer": {},
        "certificate_one_of": [
            {"type": "total_capacity"},
            {"type": "incompatible_items", "indices": ["pairwise incompatible item index"]},
        ],
    },
    "optimize": {
        "verdict": "optimal",
        "answer": {"bins": [["item index"]], "bin_count": "positive integer"},
        "certificate": "one lower bound above whose value equals bin_count",
    },
    "additional_fields": False,
}

SUBSET_TEMPLATES: dict[str, dict[str, Any]] = {
    "pair-pivot": {
        "family_id": "subset-pair-pivot-001",
        "title": "Exact subset boundary after two one-coordinate edits",
        "inputs": [
            {"numbers": [3, 4, 7, 8], "target": 11},
            {"numbers": [2, 4, 7, 8], "target": 11},
            {"numbers": [2, 4, 6, 8], "target": 11},
        ],
        "feasible_indices": [[0, 3], [1, 2]],
        "boundary_certificate": {"type": "common_divisor", "divisor": 2},
    },
    "modular-break": {
        "family_id": "subset-modular-break-001",
        "title": "Exact subset boundary created by breaking two modular choices",
        "inputs": [
            {"numbers": [4, 6, 9, 12, 14], "target": 20},
            {"numbers": [3, 6, 9, 12, 14], "target": 20},
            {"numbers": [3, 6, 9, 12, 15], "target": 20},
        ],
        "feasible_indices": [[1, 4], [1, 4]],
        "boundary_certificate": {"type": "common_divisor", "divisor": 3},
    },
    "superincreasing-gap": {
        "family_id": "subset-superincreasing-gap-001",
        "title": "Exact subset boundary in a sparse superincreasing-style system",
        "inputs": [
            {"numbers": [1, 5, 11, 22], "target": 17},
            {"numbers": [1, 5, 11, 23], "target": 17},
            {"numbers": [2, 5, 11, 23], "target": 17},
        ],
        "feasible_indices": [[0, 1, 2], [0, 1, 2]],
        "boundary_certificate": {"type": "superincreasing_greedy", "remainder": 1},
    },
}

COLORING_TEMPLATES: dict[str, dict[str, Any]] = {
    "clique-completion": {
        "family_id": "coloring-clique-completion-001",
        "title": "Three-coloring boundary completed to a four-clique",
        "vertices": ["a", "b", "c", "d"],
        "k": 3,
        "edges": [
            [["a", "b"], ["a", "c"], ["b", "c"], ["c", "d"]],
            [["a", "b"], ["a", "c"], ["b", "c"], ["b", "d"], ["c", "d"]],
            [["a", "b"], ["a", "c"], ["a", "d"], ["b", "c"], ["b", "d"], ["c", "d"]],
        ],
    },
    "odd-cycle-closure": {
        "family_id": "coloring-odd-cycle-closure-001",
        "title": "Two-coloring boundary formed by closing an odd cycle",
        "vertices": ["0", "1", "2", "3", "4"],
        "k": 2,
        "edges": [
            [["0", "1"], ["1", "2"], ["2", "3"]],
            [["0", "1"], ["1", "2"], ["2", "3"], ["3", "4"]],
            [["0", "1"], ["1", "2"], ["2", "3"], ["3", "4"], ["4", "0"]],
        ],
    },
    "odd-wheel-closure": {
        "family_id": "coloring-odd-wheel-closure-001",
        "title": "Three-coloring boundary formed by closing an odd wheel",
        "vertices": ["h", "0", "1", "2", "3", "4"],
        "k": 3,
        "edges": [
            [["h", "0"], ["h", "1"], ["h", "2"], ["h", "3"], ["h", "4"], ["0", "1"], ["1", "2"], ["2", "3"]],
            [["h", "0"], ["h", "1"], ["h", "2"], ["h", "3"], ["h", "4"], ["0", "1"], ["1", "2"], ["2", "3"], ["3", "4"]],
            [["h", "0"], ["h", "1"], ["h", "2"], ["h", "3"], ["h", "4"], ["0", "1"], ["1", "2"], ["2", "3"], ["3", "4"], ["4", "0"]],
        ],
    },
}

PACKING_TEMPLATES: dict[str, dict[str, Any]] = {
    "total-capacity": {
        "family_id": "packing-total-capacity-001",
        "title": "Two-bin boundary crossed by one unit of total load",
        "capacity": 10,
        "bin_limit": 2,
        "weights": [[4, 6, 3, 6], [4, 6, 3, 7], [4, 6, 3, 8]],
    },
    "incompatibility": {
        "family_id": "packing-incompatibility-001",
        "title": "Two-bin boundary created by a pairwise-incompatible triple",
        "capacity": 10,
        "bin_limit": 2,
        "weights": [[5, 5, 4], [6, 5, 4], [6, 5, 6]],
    },
    "balanced-load": {
        "family_id": "packing-balanced-load-001",
        "title": "Three-bin exact-load boundary crossed by one unit",
        "capacity": 12,
        "bin_limit": 3,
        "weights": [[8, 4, 7, 5, 6, 5], [8, 4, 7, 5, 6, 6], [8, 4, 7, 5, 6, 7]],
    },
}


def _family(
    family_id: str,
    title: str,
    domain: str,
    generator_id: str,
    submission_contract: dict[str, Any],
    instances: list[dict[str, Any]],
    *,
    generator_version: str = "1.0.0",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "benchmark": "constraint-shift-math",
        "family_id": family_id,
        "title": title,
        "domain": domain,
        "track": "public_dev",
        "generator": {"id": generator_id, "version": generator_version, "template": family_id},
        "submission_contract": deepcopy(submission_contract),
        "scoring": deepcopy(SCORING),
        "instances": instances,
    }


def build_subset_sum_family(template: str) -> dict[str, Any]:
    spec = SUBSET_TEMPLATES[template]
    identity = spec["family_id"]
    variants = ["base_feasible", "nearby_feasible", "boundary_infeasible"]
    instances = []
    for suffix, variant, data in zip("abc", variants, spec["inputs"]):
        instances.append({
            "id": f"{identity}-{suffix}",
            "variant": variant,
            "validator": "subset_sum_v1",
            "goal": "classify_exact_subset",
            "statement": "Classify exact subset-sum feasibility; use zero-based item indices or a short structural certificate.",
            "input": deepcopy(data),
        })
    final = deepcopy(instances[-1])
    final.update({
        "id": f"{identity}-d",
        "variant": "optimal_certificate",
        "goal": "closest_subset",
        "statement": "Find a subset with minimum absolute distance from the target and certify it structurally.",
    })
    instances.append(final)
    family = _family(
        identity,
        spec["title"],
        "discrete_optimization",
        "subset-sum-phase-templates",
        SUBSET_CONTRACT,
        instances,
        generator_version="2.0.0",
    )
    _audit_subset(family, spec)
    return family


def _audit_subset(family: dict[str, Any], spec: dict[str, Any]) -> None:
    for instance, indices in zip(family["instances"][:2], spec["feasible_indices"]):
        data = instance["input"]
        if len(indices) != len(set(indices)) or sum(data["numbers"][index] for index in indices) != data["target"]:
            raise ValueError("Subset feasible phase lacks its constructed witness")

    boundary = family["instances"][2]["input"]
    certificate = spec["boundary_certificate"]
    if certificate["type"] == "common_divisor":
        divisor = certificate["divisor"]
        certified = all(number % divisor == 0 for number in boundary["numbers"]) and boundary["target"] % divisor != 0
    else:
        prefix = 0
        certified = True
        for number in boundary["numbers"]:
            if number <= prefix:
                certified = False
                break
            prefix += number
        remainder = boundary["target"]
        for number in reversed(boundary["numbers"]):
            if number <= remainder:
                remainder -= number
        certified = certified and remainder == certificate["remainder"] and remainder > 0
    if not certified:
        raise ValueError("Subset boundary lacks its linear structural certificate")


def build_coloring_family(template: str) -> dict[str, Any]:
    spec = COLORING_TEMPLATES[template]
    identity = spec["family_id"]
    instances = []
    for suffix, variant, edges in zip("abc", ["base_feasible", "nearby_feasible", "boundary_infeasible"], spec["edges"]):
        instances.append({
            "id": f"{identity}-{suffix}",
            "variant": variant,
            "validator": "graph_coloring_v1",
            "goal": "classify_k_coloring",
            "statement": "Classify k-colorability and return either a coloring or the specified structural obstruction.",
            "input": {"vertices": deepcopy(spec["vertices"]), "edges": deepcopy(edges), "k": spec["k"]},
        })
    final = deepcopy(instances[-1])
    final.update({
        "id": f"{identity}-d",
        "variant": "optimal_certificate",
        "goal": "minimum_coloring",
        "statement": "Find a minimum coloring and certify a matching structural lower bound.",
    })
    instances.append(final)
    family = _family(
        identity,
        spec["title"],
        "graph_theory",
        "coloring-phase-templates",
        COLORING_CONTRACT,
        instances,
    )
    _audit_coloring(family)
    return family


def _colorable(vertices: list[str], edges: list[list[str]], k: int) -> bool:
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    for colors in product(range(k), repeat=len(vertices)):
        if all(colors[positions[left]] != colors[positions[right]] for left, right in edges):
            return True
    return False


def _audit_coloring(family: dict[str, Any]) -> None:
    values = []
    for instance in family["instances"][:3]:
        data = instance["input"]
        values.append(_colorable(data["vertices"], data["edges"], data["k"]))
    if values != [True, True, False]:
        raise ValueError(f"Coloring phase contract failed: {values}")


def build_packing_family(template: str) -> dict[str, Any]:
    spec = PACKING_TEMPLATES[template]
    identity = spec["family_id"]
    instances = []
    for suffix, variant, weights in zip("abc", ["base_feasible", "nearby_feasible", "boundary_infeasible"], spec["weights"]):
        instances.append({
            "id": f"{identity}-{suffix}",
            "variant": variant,
            "validator": "bin_packing_v1",
            "goal": "classify_bin_limit",
            "statement": "Classify whether all indexed items fit within the bin limit and provide a witness or lower-bound certificate.",
            "input": {"weights": deepcopy(weights), "capacity": spec["capacity"], "bin_limit": spec["bin_limit"]},
        })
    final = deepcopy(instances[-1])
    final.update({
        "id": f"{identity}-d",
        "variant": "optimal_certificate",
        "goal": "minimum_bins",
        "statement": "Find a minimum-bin packing and provide a lower bound of the same size.",
    })
    instances.append(final)
    family = _family(
        identity,
        spec["title"],
        "packing",
        "bin-packing-phase-templates",
        PACKING_CONTRACT,
        instances,
    )
    _audit_packing(family)
    return family


def _can_pack(weights: list[int], capacity: int, limit: int) -> bool:
    loads = [0] * limit
    ordered = sorted(weights, reverse=True)

    def search(index: int) -> bool:
        if index == len(ordered):
            return True
        weight = ordered[index]
        seen: set[int] = set()
        for bin_index, load in enumerate(loads):
            if load in seen or load + weight > capacity:
                continue
            seen.add(load)
            loads[bin_index] += weight
            if search(index + 1):
                return True
            loads[bin_index] -= weight
        return False

    return search(0)


def _audit_packing(family: dict[str, Any]) -> None:
    values = []
    for instance in family["instances"][:3]:
        data = instance["input"]
        values.append(_can_pack(data["weights"], data["capacity"], data["bin_limit"]))
    if values != [True, True, False]:
        raise ValueError(f"Packing phase contract failed: {values}")


BUILDERS = {
    **{name: (lambda key=name: build_subset_sum_family(key)) for name in SUBSET_TEMPLATES},
    **{name: (lambda key=name: build_coloring_family(key)) for name in COLORING_TEMPLATES},
    **{name: (lambda key=name: build_packing_family(key)) for name in PACKING_TEMPLATES},
}
