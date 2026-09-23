from __future__ import annotations

from collections import deque
from copy import deepcopy
import random
from typing import Any

from benchcore import canonical_sha256


GENERATOR_ID = "bipartite-phase-family"
GENERATOR_VERSION = "2.0.0"
MATCHING_CONTRACT = {
    "top_level_fields": ["instance_id", "verdict", "answer", "certificate"],
    "classify_feasible": {
        "verdict": "feasible",
        "answer": {"matching": [["left vertex", "right vertex"]]},
        "certificate": {},
    },
    "classify_infeasible": {
        "verdict": "infeasible",
        "answer": {},
        "certificate": {"hall_subset": ["left vertex"]},
    },
    "optimize": {
        "verdict": "optimal",
        "answer": {"matching": [["left vertex", "right vertex"]]},
        "certificate": {
            "minimum_vertex_cover": {
                "left": ["left vertex"],
                "right": ["right vertex"],
            }
        },
    },
    "additional_fields": False,
}


MIN_SIZE = 4
MAX_SIZE = 2000
DEFAULT_SIZE = 32
_TRACKS = {"public_dev", "static_hidden", "fresh_private", "retired"}
_CLASSIFY_STATEMENT = (
    "Decide whether the bipartite graph admits a perfect matching. Return a matching witness "
    "when it does, or a Hall-subset obstruction when it does not."
)
_OPTIMIZE_STATEMENT = "Return a maximum matching and an equal-size minimum vertex cover."


# ---------------------------------------------------------------------------
# Polynomial-time matching primitives (Hopcroft-Karp + Koenig)
# ---------------------------------------------------------------------------

def _adjacency(left: list[str], edges: list[list[str]]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {vertex: [] for vertex in left}
    for source, target in edges:
        adjacency[source].append(target)
    for targets in adjacency.values():
        targets.sort()
    return adjacency


def maximum_matching(left: list[str], right: list[str], edges: list[list[str]]) -> dict[str, str]:
    """Return a maximum matching as ``{left: right}`` using Hopcroft-Karp."""
    adjacency = _adjacency(left, edges)
    match_left: dict[str, str | None] = {vertex: None for vertex in left}
    match_right: dict[str, str | None] = {vertex: None for vertex in right}
    infinity = len(left) + 1

    while True:
        distance: dict[str, int] = {}
        queue: deque[str] = deque()
        for vertex in left:
            if match_left[vertex] is None:
                distance[vertex] = 0
                queue.append(vertex)
            else:
                distance[vertex] = infinity
        found = False
        while queue:
            vertex = queue.popleft()
            for target in adjacency[vertex]:
                partner = match_right[target]
                if partner is None:
                    found = True
                elif distance[partner] == infinity:
                    distance[partner] = distance[vertex] + 1
                    queue.append(partner)
        if not found:
            break
        for root in left:
            if match_left[root] is not None:
                continue
            # Iterative layered DFS so large instances never hit recursion limits.
            stack: list[tuple[str, int]] = [(root, 0)]
            path: list[tuple[str, str]] = []
            while stack:
                vertex, position = stack[-1]
                targets = adjacency[vertex]
                if position >= len(targets):
                    distance[vertex] = infinity
                    stack.pop()
                    if path:
                        path.pop()
                    continue
                stack[-1] = (vertex, position + 1)
                target = targets[position]
                partner = match_right[target]
                if partner is None:
                    path.append((vertex, target))
                    for a, b in path:
                        match_left[a] = b
                        match_right[b] = a
                    break
                if distance[partner] == distance[vertex] + 1:
                    path.append((vertex, target))
                    stack.append((partner, 0))
    return {a: b for a, b in match_left.items() if b is not None}


def koenig_certificate(
    left: list[str], right: list[str], edges: list[list[str]], matching: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(cover_left, cover_right, hall_subset)`` from a maximum matching.

    ``hall_subset`` is empty exactly when the matching is perfect on the left side.
    """
    adjacency = _adjacency(left, edges)
    match_right = {b: a for a, b in matching.items()}
    free = [vertex for vertex in left if vertex not in matching]
    reached_left = set(free)
    reached_right: set[str] = set()
    queue = deque(free)
    while queue:
        vertex = queue.popleft()
        for target in adjacency[vertex]:
            if target in reached_right or matching.get(vertex) == target:
                continue
            reached_right.add(target)
            partner = match_right.get(target)
            if partner is not None and partner not in reached_left:
                reached_left.add(partner)
                queue.append(partner)
    cover_left = sorted(vertex for vertex in left if vertex not in reached_left)
    cover_right = sorted(reached_right)
    hall_subset = sorted(reached_left) if free else []
    return cover_left, cover_right, hall_subset


# ---------------------------------------------------------------------------
# Family generator
# ---------------------------------------------------------------------------

def _labels(rng: random.Random, prefix: str, count: int) -> list[str]:
    width = max(3, len(str(count * 10)))
    low, high = 10 ** (width - 1), 10**width
    return [f"{prefix}{value}" for value in rng.sample(range(low, high), count)]


def build_matching_family(
    seed: int,
    *,
    size: int | None = None,
    family_id: str | None = None,
    track: str = "fresh_private",
    disclose_seed: bool = False,
) -> dict[str, Any]:
    """Generate a randomized four-instance perfect-matching family.

    A hidden tight Hall set ``S`` (``|N(S)| == |S|``) is planted inside a random
    graph that still has a planted perfect matching. Exactly one right vertex of
    ``N(S)`` is reachable from ``S`` through a single *critical* edge; deleting that
    edge makes ``S`` a Hall violator. A second *harmless* edge lies outside the
    planted matching and never changes feasibility. Consecutive instances differ
    by one edge, and the composition (two feasible + one infeasible, or one
    feasible + two infeasible) is drawn from the seed. The size of ``S``, the
    graph density, labels, and edge order are all randomized, so no fixed
    template is shared between seeds.
    """
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("seed must be an integer in [0, 2**63)")
    if track not in _TRACKS:
        raise ValueError("unknown track")
    n = DEFAULT_SIZE if size is None else size
    if type(n) is not int or not MIN_SIZE <= n <= MAX_SIZE:
        raise ValueError(f"size must be an integer in [{MIN_SIZE}, {MAX_SIZE}]")

    rng = random.Random(seed)
    left = _labels(rng, "L", n)
    right = _labels(rng, "R", n)

    k = rng.randint(2, max(2, n // 2))
    k = min(k, n - 1)
    hall_left = rng.sample(left, k)
    hall_left_set = set(hall_left)
    outside_left = [vertex for vertex in left if vertex not in hall_left_set]
    hall_right = rng.sample(right, k)
    hall_right_set = set(hall_right)
    outside_right = [vertex for vertex in right if vertex not in hall_right_set]
    rng.shuffle(outside_right)

    planted = dict(zip(hall_left, hall_right))
    planted.update(zip(outside_left, outside_right))
    critical_right = hall_right[0]
    critical_left = hall_left[0]
    critical_edge = (critical_left, critical_right)

    edge_set: set[tuple[str, str]] = set(planted.items())
    degree = rng.randint(2, 4)
    inner_targets = [vertex for vertex in hall_right if vertex != critical_right]
    for vertex in hall_left:
        # S only reaches N(S); only critical_left may reach critical_right.
        extra = min(len(inner_targets), rng.randint(1, degree))
        for target in rng.sample(inner_targets, extra):
            edge_set.add((vertex, target))
    for vertex in outside_left:
        for target in rng.sample(right, min(n, rng.randint(1, degree))):
            edge_set.add((vertex, target))
    # Hide the critical right vertex among ordinary-looking degrees.
    helpers = rng.sample(outside_left, min(len(outside_left), rng.randint(1, 2)))
    for vertex in helpers:
        edge_set.add((vertex, critical_right))

    harmless_pool = sorted(
        edge
        for edge in edge_set
        if edge[0] in outside_left and planted[edge[0]] != edge[1]
    )
    if not harmless_pool:
        vertex = rng.choice(outside_left)
        target = rng.choice([t for t in right if t != planted[vertex]])
        edge_set.add((vertex, target))
        harmless_pool = [(vertex, target)]
    harmless_edge = rng.choice(harmless_pool)

    full = sorted(edge_set)
    two_feasible = rng.random() < 0.5
    if two_feasible:
        stages = [full, [e for e in full if e != harmless_edge]]
        stages.append([e for e in stages[1] if e != critical_edge])
        variants = ("base_feasible", "nearby_feasible", "boundary_infeasible")
        composition = "F,F,I,O"
    else:
        stages = [full, [e for e in full if e != critical_edge]]
        stages.append([e for e in stages[1] if e != harmless_edge])
        variants = ("base_feasible", "boundary_infeasible", "nearby_infeasible")
        composition = "F,I,I,O"

    def render(indices: list[tuple[str, str]]) -> list[list[str]]:
        result = [[a, b] for a, b in indices]
        rng.shuffle(result)
        return result

    rendered = [render(stage) for stage in stages]
    identity = family_id or f"matching-phase-{seed:016x}"
    instances = []
    for suffix, variant, edges in zip("abc", variants, rendered):
        instances.append(
            {
                "id": f"{identity}-{suffix}",
                "variant": variant,
                "validator": "bipartite_matching_v1",
                "goal": "classify_perfect_matching",
                "statement": _CLASSIFY_STATEMENT,
                "input": {"left": list(left), "right": list(right), "edges": edges},
            }
        )
    instances.append(
        {
            "id": f"{identity}-d",
            "variant": "optimal_certificate",
            "validator": "bipartite_matching_v1",
            "goal": "maximum_matching",
            "statement": _OPTIMIZE_STATEMENT,
            "input": deepcopy(instances[2]["input"]),
        }
    )
    generator: dict[str, Any] = {
        "id": GENERATOR_ID,
        "version": GENERATOR_VERSION,
        "template": "seeded-planted-hall-phase-boundary",
        "size": n,
        "composition": composition,
        "commitment_scheme": "sha256-canonical-family-without-generation-payload-sha256",
    }
    if disclose_seed:
        generator["seed"] = seed
    else:
        generator["private_seed_required"] = True
    family = {
        "schema_version": 1,
        "benchmark": "constraint-shift-math",
        "family_id": identity,
        "title": "Perfect matching across a feasibility phase boundary",
        "domain": "combinatorics",
        "track": track,
        "generator": generator,
        "submission_contract": deepcopy(MATCHING_CONTRACT),
        "scoring": {"correctness_weight": 70, "all_correct_bonus": 30},
        "instances": instances,
    }
    audit_matching_family(family)
    # Commit to exactly the generated payload that existed before the digest
    # field was inserted. Naming the exclusion avoids an impossible self-hash
    # and lets release tooling independently reproduce the commitment.
    family["generator"]["generation_payload_sha256"] = canonical_sha256(family)
    return family


def _edge_difference(first: dict[str, Any], second: dict[str, Any]) -> int:
    a = {tuple(edge) for edge in first["edges"]}
    b = {tuple(edge) for edge in second["edges"]}
    return len(a ^ b)


def audit_matching_family(family: dict[str, Any]) -> None:
    """Independently re-derive every instance's status; raise on any drift."""
    instances = family["instances"]
    if len(instances) != 4:
        raise ValueError("Matching family must contain four instances")
    expected = []
    for instance in instances[:3]:
        expected.append(instance["variant"].endswith("_feasible"))
    if expected[0] is not True or expected[2] is not False:
        raise ValueError(f"Unsupported matching composition: {expected}")
    for index, instance in enumerate(instances):
        data = instance["input"]
        n = len(data["left"])
        matching = maximum_matching(data["left"], data["right"], data["edges"])
        _, _, hall_subset = koenig_certificate(data["left"], data["right"], data["edges"], matching)
        feasible = len(matching) == n
        if index < 3 and feasible != expected[index]:
            raise ValueError(f"Generator phase contract failed at instance {index}")
        if not feasible and not hall_subset:
            raise ValueError("Infeasible instance lacks a Hall obstruction")
    for first, second in zip(instances[:2], instances[1:3]):
        if _edge_difference(first["input"], second["input"]) != 1:
            raise ValueError("Consecutive classification instances must differ by one edge")
    if instances[2]["input"] != instances[3]["input"]:
        raise ValueError("Optimization instance must reuse the last classification input")


def matching_reference_rows(family: dict[str, Any]) -> list[dict[str, Any]]:
    """Solve every instance of a matching family and emit certificate rows.

    Operators use this to produce evaluator-side reference submissions; it is
    also the end-to-end self-test for the generator and validator.
    """
    rows = []
    for instance in family["instances"]:
        data = instance["input"]
        matching = maximum_matching(data["left"], data["right"], data["edges"])
        cover_left, cover_right, hall_subset = koenig_certificate(
            data["left"], data["right"], data["edges"], matching
        )
        pairs = [[a, b] for a, b in sorted(matching.items())]
        if instance["goal"] == "maximum_matching":
            row = {
                "verdict": "optimal",
                "answer": {"matching": pairs},
                "certificate": {"minimum_vertex_cover": {"left": cover_left, "right": cover_right}},
            }
        elif len(matching) == len(data["left"]):
            row = {"verdict": "feasible", "answer": {"matching": pairs}, "certificate": {}}
        else:
            row = {"verdict": "infeasible", "answer": {}, "certificate": {"hall_subset": hall_subset}}
        rows.append({"instance_id": instance["id"], **row})
    return rows
