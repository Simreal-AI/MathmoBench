from __future__ import annotations

from math import ceil
from typing import Any

from .validators import ValidationResult


def _integer_list(value: Any) -> bool:
    return isinstance(value, list) and all(type(item) is int for item in value)


def _problem(instance: dict[str, Any]) -> tuple[list[int], int, int]:
    data = instance.get("input")
    if not isinstance(data, dict):
        raise ValueError("Bin-packing input must be an object")
    weights = data.get("weights")
    capacity = data.get("capacity")
    bin_limit = data.get("bin_limit")
    if (
        not _integer_list(weights)
        or not weights
        or type(capacity) is not int
        or capacity <= 0
        or type(bin_limit) is not int
        or bin_limit <= 0
    ):
        raise ValueError("Bin-packing needs fitting positive weights, capacity, and bin_limit")
    if any(weight <= 0 or weight > capacity for weight in weights):
        raise ValueError("Bin-packing needs fitting positive weights, capacity, and bin_limit")
    return weights, capacity, bin_limit


def _valid_bins(value: Any, weights: list[int], capacity: int) -> tuple[bool, int]:
    if not isinstance(value, list) or not value:
        return False, 0
    flattened: list[int] = []
    for bucket in value:
        if not _integer_list(bucket) or not bucket:
            return False, 0
        flattened.extend(bucket)
        if len(bucket) != len(set(bucket)):
            return False, 0
        if any(index < 0 or index >= len(weights) for index in bucket):
            return False, 0
        if sum(weights[index] for index in bucket) > capacity:
            return False, 0
    return sorted(flattened) == list(range(len(weights))), len(value)


def _certificate_lower_bound(certificate: dict[str, Any], weights: list[int], capacity: int) -> int | None:
    kind = certificate.get("type")
    if kind == "total_capacity" and set(certificate) == {"type"}:
        return ceil(sum(weights) / capacity)
    if kind == "incompatible_items" and set(certificate) == {"type", "indices"}:
        indices = certificate.get("indices")
        if (
            not _integer_list(indices)
            or not indices
            or len(indices) != len(set(indices))
            or any(index < 0 or index >= len(weights) for index in indices)
        ):
            return None
        if all(weights[indices[i]] + weights[indices[j]] > capacity for i in range(len(indices)) for j in range(i + 1, len(indices))):
            return len(indices)
    return None


def validate_bin_packing(instance: dict[str, Any], submission: dict[str, Any]) -> ValidationResult:
    required = {"instance_id", "verdict", "answer", "certificate"}
    compliant = set(submission) == required and submission.get("instance_id") == instance.get("id")
    if not compliant:
        return ValidationResult(False, False, "missing required fields or wrong instance_id")
    if not isinstance(submission["answer"], dict) or not isinstance(submission["certificate"], dict):
        return ValidationResult(False, False, "answer and certificate must be objects")

    weights, capacity, bin_limit = _problem(instance)
    goal = instance.get("goal")
    verdict = submission.get("verdict")

    if goal == "classify_bin_limit" and verdict == "feasible":
        if set(submission["answer"]) != {"bins"} or submission["certificate"]:
            return ValidationResult(False, False, "feasible output needs only answer.bins")
        valid, count = _valid_bins(submission["answer"].get("bins"), weights, capacity)
        correct = valid and count <= bin_limit
        return ValidationResult(correct, True, "valid packing within the bin limit" if correct else "invalid packing")

    if goal == "classify_bin_limit" and verdict == "infeasible":
        if submission["answer"]:
            return ValidationResult(False, False, "infeasible output must have an empty answer")
        lower_bound = _certificate_lower_bound(submission["certificate"], weights, capacity)
        correct = lower_bound is not None and lower_bound > bin_limit
        return ValidationResult(correct, True, "lower-bound certificate exceeds the bin limit" if correct else "invalid packing obstruction")

    if goal == "minimum_bins" and verdict == "optimal":
        if set(submission["answer"]) != {"bins", "bin_count"}:
            return ValidationResult(False, False, "optimal answer needs bins and bin_count")
        valid, count = _valid_bins(submission["answer"].get("bins"), weights, capacity)
        claimed = submission["answer"].get("bin_count")
        lower_bound = _certificate_lower_bound(submission["certificate"], weights, capacity)
        correct = valid and type(claimed) is int and claimed == count and lower_bound == count
        return ValidationResult(correct, True, "packing and lower bound meet at the optimum" if correct else "invalid optimal packing proof")

    return ValidationResult(False, True, "verdict is unsupported for this goal")


VALIDATORS = {"bin_packing_v1": validate_bin_packing}
