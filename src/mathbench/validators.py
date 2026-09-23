from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    correct: bool
    schema_compliant: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _pairs(value: Any) -> list[tuple[str, str]] | None:
    if not isinstance(value, list):
        return None
    output: list[tuple[str, str]] = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(x, str) for x in pair):
            return None
        output.append((pair[0], pair[1]))
    return output


def _graph(instance: dict[str, Any]) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    data = instance.get("input")
    if not isinstance(data, dict) or not _string_list(data.get("left")) or not _string_list(data.get("right")):
        raise ValueError("Task graph needs left and right string lists")
    left, right = set(data["left"]), set(data["right"])
    if len(left) != len(data["left"]) or len(right) != len(data["right"]) or left & right:
        raise ValueError("Task vertices must be unique and partitions disjoint")
    edges = _pairs(data.get("edges"))
    if edges is None or any(a not in left or b not in right for a, b in edges):
        raise ValueError("Task edges must connect declared left and right vertices")
    return left, right, set(edges)


def _valid_matching(
    matching: Any, left: set[str], right: set[str], edges: set[tuple[str, str]]
) -> tuple[bool, list[tuple[str, str]]]:
    pairs = _pairs(matching)
    if pairs is None:
        return False, []
    used_left = [a for a, _ in pairs]
    used_right = [b for _, b in pairs]
    valid = (
        len(used_left) == len(set(used_left))
        and len(used_right) == len(set(used_right))
        and all(a in left and b in right and (a, b) in edges for a, b in pairs)
    )
    return valid, pairs


def validate_bipartite(instance: dict[str, Any], submission: dict[str, Any]) -> ValidationResult:
    required = {"instance_id", "verdict", "answer", "certificate"}
    compliant = set(submission) == required and submission.get("instance_id") == instance.get("id")
    if not compliant:
        return ValidationResult(False, False, "missing required fields or wrong instance_id")
    if not isinstance(submission["answer"], dict) or not isinstance(submission["certificate"], dict):
        return ValidationResult(False, False, "answer and certificate must be objects")

    left, right, edges = _graph(instance)
    goal = instance.get("goal")
    verdict = submission["verdict"]

    if goal == "classify_perfect_matching" and verdict == "feasible":
        if set(submission["answer"]) != {"matching"} or submission["certificate"]:
            return ValidationResult(False, False, "feasible output has unknown or misplaced fields")
        valid, matching = _valid_matching(submission["answer"].get("matching"), left, right, edges)
        perfect = valid and len(matching) == len(left) == len(right)
        return ValidationResult(perfect, True, "valid perfect matching" if perfect else "invalid perfect matching")

    if goal == "classify_perfect_matching" and verdict == "infeasible":
        if submission["answer"] or set(submission["certificate"]) != {"hall_subset"}:
            return ValidationResult(False, False, "infeasible output needs only hall_subset")
        subset = submission["certificate"].get("hall_subset")
        if not _string_list(subset) or not subset:
            return ValidationResult(False, True, "Hall certificate must contain a non-empty string list")
        subset_set = set(subset)
        actual_neighbors = {b for a, b in edges if a in subset_set}
        valid = (
            len(subset_set) == len(subset)
            and subset_set <= left
            and len(actual_neighbors) < len(subset_set)
        )
        return ValidationResult(valid, True, "valid Hall obstruction" if valid else "invalid Hall obstruction")

    if goal == "maximum_matching" and verdict == "optimal":
        if set(submission["answer"]) != {"matching"} or set(submission["certificate"]) != {"minimum_vertex_cover"}:
            return ValidationResult(False, False, "optimal output has unknown or missing fields")
        valid, matching = _valid_matching(submission["answer"].get("matching"), left, right, edges)
        cover = submission["certificate"].get("minimum_vertex_cover")
        if (
            not isinstance(cover, dict)
            or set(cover) != {"left", "right"}
            or not _string_list(cover.get("left"))
            or not _string_list(cover.get("right"))
        ):
            return ValidationResult(False, True, "minimum_vertex_cover needs left and right lists")
        cover_left, cover_right = set(cover["left"]), set(cover["right"])
        cover_valid = (
            len(cover_left) == len(cover["left"])
            and len(cover_right) == len(cover["right"])
            and cover_left <= left
            and cover_right <= right
            and all(a in cover_left or b in cover_right for a, b in edges)
        )
        optimal = valid and cover_valid and len(matching) == len(cover_left) + len(cover_right)
        return ValidationResult(
            optimal,
            True,
            "matching and equal-size vertex-cover certificate prove optimality"
            if optimal
            else "invalid matching or optimality certificate",
        )

    return ValidationResult(False, True, "verdict is unsupported for this goal")
