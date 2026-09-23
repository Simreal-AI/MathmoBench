from __future__ import annotations

from typing import Any

from .validators import ValidationResult


def _integer_list(value: Any) -> bool:
    return isinstance(value, list) and all(type(item) is int for item in value)


def _problem(instance: dict[str, Any]) -> tuple[list[int], int]:
    data = instance.get("input")
    if not isinstance(data, dict):
        raise ValueError("Subset-sum input must be an object")
    numbers = data.get("numbers")
    target = data.get("target")
    if (
        not _integer_list(numbers)
        or not numbers
        or any(number <= 0 for number in numbers)
        or type(target) is not int
    ):
        raise ValueError("Subset-sum needs positive integer numbers and an integer target")
    return numbers, target


def _selection(indices: Any, numbers: list[int]) -> tuple[bool, int]:
    if not _integer_list(indices):
        return False, 0
    if len(indices) != len(set(indices)) or any(index < 0 or index >= len(numbers) for index in indices):
        return False, 0
    return True, sum(numbers[index] for index in indices)


def _certificate_schema(certificate: dict[str, Any]) -> bool:
    kind = certificate.get("type")
    if kind == "common_divisor":
        return set(certificate) == {"type", "divisor"}
    if kind == "superincreasing_greedy":
        return set(certificate) == {"type", "remainder"}
    return False


def _common_divisor_bound(numbers: list[int], target: int, certificate: dict[str, Any]) -> int | None:
    divisor = certificate.get("divisor")
    if type(divisor) is not int or divisor <= 1 or any(number % divisor for number in numbers):
        return None
    remainder = target % divisor
    return min(remainder, divisor - remainder)


def _superincreasing_bounds(numbers: list[int], target: int) -> tuple[int, int] | None:
    """Return greedy remainder and exact closest distance in linear time."""
    if target < 0:
        return None
    prefix = 0
    for number in numbers:
        if number <= prefix:
            return None
        prefix += number

    remaining = target
    selected = [False] * len(numbers)
    for index in range(len(numbers) - 1, -1, -1):
        if numbers[index] <= remaining:
            selected[index] = True
            remaining -= numbers[index]

    lower_total = target - remaining
    selected_prefix = 0
    upper_total: int | None = None
    for index, chosen in enumerate(selected):
        if not chosen:
            upper_total = lower_total - selected_prefix + numbers[index]
            break
        selected_prefix += numbers[index]

    optimum = remaining
    if upper_total is not None:
        optimum = min(optimum, upper_total - target)
    return remaining, optimum


def _certificate_claim(
    numbers: list[int],
    target: int,
    certificate: dict[str, Any],
) -> tuple[bool, bool, int | None]:
    """Return proof validity, exact-target infeasibility, and an optimum bound."""
    if certificate["type"] == "common_divisor":
        bound = _common_divisor_bound(numbers, target, certificate)
        return bound is not None, bool(bound), bound

    bounds = _superincreasing_bounds(numbers, target)
    remainder = certificate.get("remainder")
    if bounds is None or type(remainder) is not int or remainder < 0 or remainder != bounds[0]:
        return False, False, None
    return True, remainder != 0, bounds[1]


def validate_subset_sum(instance: dict[str, Any], submission: dict[str, Any]) -> ValidationResult:
    required = {"instance_id", "verdict", "answer", "certificate"}
    compliant = set(submission) == required and submission.get("instance_id") == instance.get("id")
    if not compliant:
        return ValidationResult(False, False, "missing required fields or wrong instance_id")
    if not isinstance(submission["answer"], dict) or not isinstance(submission["certificate"], dict):
        return ValidationResult(False, False, "answer and certificate must be objects")

    numbers, target = _problem(instance)
    goal = instance.get("goal")
    verdict = submission.get("verdict")

    if goal == "classify_exact_subset" and verdict == "feasible":
        if set(submission["answer"]) != {"indices"} or submission["certificate"]:
            return ValidationResult(False, False, "feasible output needs only answer.indices")
        valid, total = _selection(submission["answer"].get("indices"), numbers)
        correct = valid and total == target
        return ValidationResult(correct, True, "valid exact subset" if correct else "invalid exact subset")

    if goal == "classify_exact_subset" and verdict == "infeasible":
        if submission["answer"]:
            return ValidationResult(False, False, "infeasible output requires an empty answer")
        if not _certificate_schema(submission["certificate"]):
            return ValidationResult(False, False, "infeasible output needs one supported structural certificate")
        proof_valid, proves_infeasible, _ = _certificate_claim(numbers, target, submission["certificate"])
        correct = proof_valid and proves_infeasible
        return ValidationResult(
            correct,
            True,
            "short structural certificate excludes target" if correct else "invalid infeasibility certificate",
        )

    if goal == "closest_subset" and verdict == "optimal":
        if set(submission["answer"]) != {"indices", "distance"}:
            return ValidationResult(False, False, "optimal answer needs indices and distance")
        if not _certificate_schema(submission["certificate"]):
            return ValidationResult(False, False, "optimal output needs one supported structural certificate")
        proof_valid, _, optimum = _certificate_claim(numbers, target, submission["certificate"])
        valid, total = _selection(submission["answer"].get("indices"), numbers)
        distance = submission["answer"].get("distance")
        correct = (
            proof_valid
            and valid
            and type(distance) is int
            and distance >= 0
            and distance == abs(total - target)
            and distance == optimum
        )
        return ValidationResult(correct, True, "subset and structural certificate prove optimal distance" if correct else "invalid closest-subset proof")

    return ValidationResult(False, True, "verdict is unsupported for this goal")


VALIDATORS = {"subset_sum_v1": validate_subset_sum}
