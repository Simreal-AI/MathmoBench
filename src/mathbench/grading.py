from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any

from benchcore import canonical_sha256, file_sha256
from .validators import validate_bipartite
from .validators_bin_packing import VALIDATORS as BIN_PACKING_VALIDATORS
from .validators_coloring import VALIDATORS as COLORING_VALIDATORS
from .validators_subset_sum import VALIDATORS as SUBSET_SUM_VALIDATORS


VALIDATORS = {
    "bipartite_matching_v1": validate_bipartite,
    **SUBSET_SUM_VALIDATORS,
    **COLORING_VALIDATORS,
    **BIN_PACKING_VALIDATORS,
}


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _protocol_scoring(protocol: dict[str, Any]) -> tuple[float, float, float]:
    if not isinstance(protocol, dict) or protocol.get("schema_version") != 1:
        raise ValueError("Unsupported protocol schema")
    if protocol.get("frozen") is not True:
        raise ValueError("Protocol must be frozen")
    math_protocol = protocol.get("math")
    if not isinstance(math_protocol, dict) or math_protocol.get("benchmark") != "constraint-shift-math":
        raise ValueError("Protocol lacks the constraint-shift-math contract")
    item_weight = math_protocol.get("item_pass_weight")
    family_weight = math_protocol.get("family_strict_pass_weight")
    if (
        not _number(item_weight)
        or not _number(family_weight)
        or float(item_weight) < 0
        or float(family_weight) < 0
        or abs(float(item_weight) + float(family_weight) - 1.0) > 1e-12
    ):
        raise ValueError("Protocol math weights must be nonnegative and sum to one")
    aggregation = protocol.get("aggregation")
    if not isinstance(aggregation, dict) or not _number(aggregation.get("invalid_submission_score")):
        raise ValueError("Protocol lacks a finite invalid-submission score")
    invalid_score = float(aggregation["invalid_submission_score"])
    return float(item_weight), float(family_weight), invalid_score


def _validate_family(
    family: dict[str, Any],
    item_weight: float,
    family_weight: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    if (
        not isinstance(family, dict)
        or family.get("schema_version") != 1
        or family.get("benchmark") != "constraint-shift-math"
        or not isinstance(family.get("family_id"), str)
        or not family["family_id"]
        or not isinstance(family.get("instances"), list)
    ):
        raise ValueError("Unsupported family schema")
    instances = family["instances"]
    if not instances or any(not isinstance(instance, dict) for instance in instances):
        raise ValueError("A family needs object-valued instances")
    ids: list[str] = []
    for instance in instances:
        identity = instance.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("Instance IDs must be unique strings")
        ids.append(identity)
        if instance.get("validator") not in VALIDATORS:
            raise ValueError(f"Unknown validator: {instance.get('validator')}")
    if len(set(ids)) != len(ids):
        raise ValueError("Instance IDs must be unique strings")

    # Legacy task-local weights are declarations only. The frozen protocol is
    # authoritative, and any retained declaration must agree with it exactly.
    scoring = family.get("scoring")
    if scoring is not None:
        if not isinstance(scoring, dict):
            raise ValueError("Family scoring declaration must be an object")
        correctness_weight = scoring.get("correctness_weight")
        strict_weight = scoring.get("all_correct_bonus")
        if (
            not _number(correctness_weight)
            or not _number(strict_weight)
            or abs(float(correctness_weight) / 100.0 - item_weight) > 1e-12
            or abs(float(strict_weight) / 100.0 - family_weight) > 1e-12
        ):
            raise ValueError("Family scoring declaration differs from the frozen protocol")
    return instances, ids


def _evaluator_sha256() -> str:
    source_root = Path(__file__).resolve().parents[1]
    files = {
        "benchcore/__init__.py": source_root / "benchcore/__init__.py",
        "benchcore/io.py": source_root / "benchcore/io.py",
        "mathbench/__init__.py": Path(__file__).with_name("__init__.py"),
        "mathbench/cli.py": Path(__file__).with_name("cli.py"),
        "mathbench/grading.py": Path(__file__),
        "mathbench/projection.py": Path(__file__).with_name("projection.py"),
        "mathbench/validators.py": Path(__file__).with_name("validators.py"),
        "mathbench/validators_subset_sum.py": Path(__file__).with_name("validators_subset_sum.py"),
        "mathbench/validators_coloring.py": Path(__file__).with_name("validators_coloring.py"),
        "mathbench/validators_bin_packing.py": Path(__file__).with_name("validators_bin_packing.py"),
    }
    return canonical_sha256({name: file_sha256(path) for name, path in sorted(files.items())})


def _receipt(
    *,
    family: dict[str, Any],
    protocol: dict[str, Any],
    submission_sha256: str | None,
    evaluator_sha256: str,
    item_weight: float,
    family_weight: float,
    results: list[dict[str, Any]],
    invalid_submission: bool,
    invalid_reason: str | None,
    invalid_score: float,
    agent_projection_sha256: str | None,
    agent_binding_sha256: str | None,
) -> dict[str, Any]:
    correctness = sum(bool(row["correct"]) for row in results) / len(results)
    compliance = sum(bool(row["schema_compliant"]) for row in results) / len(results)
    all_correct = not invalid_submission and all(bool(row["correct"]) for row in results)
    score = (
        invalid_score
        if invalid_submission
        else round(100.0 * (item_weight * correctness + family_weight * float(all_correct)), 12)
    )
    receipt = {
        "schema_version": 1,
        "benchmark": "constraint-shift-math",
        "family_id": family["family_id"],
        "family_sha256": canonical_sha256(family),
        "protocol_sha256": canonical_sha256(protocol),
        "evaluator_sha256": evaluator_sha256,
        "submission_sha256": submission_sha256,
        "agent_projection_sha256": agent_projection_sha256,
        "agent_binding_sha256": agent_binding_sha256,
        "invalid_submission": invalid_submission,
        "invalid_reason": invalid_reason,
        "scoring_weights": {
            "item_pass_weight": item_weight,
            "family_strict_pass_weight": family_weight,
        },
        "instance_count": len(results),
        "correctness_rate": correctness,
        "schema_compliance_rate": compliance,
        "all_correct": all_correct,
        "family_strict_pass": float(all_correct),
        "score": score,
        "results": results,
    }
    return {**receipt, "receipt_sha256": canonical_sha256(receipt)}


def grade_family(
    family: dict[str, Any],
    submissions: list[dict[str, Any]],
    protocol: dict[str, Any],
    *,
    submission_error: str | None = None,
    submission_sha256: str | None = None,
    agent_projection_sha256: str | None = None,
    agent_binding_sha256: str | None = None,
) -> dict[str, Any]:
    """Grade one family, converting submission faults into zero-score receipts.

    Invalid task, protocol, evaluator, or validator configuration still raises:
    those are infrastructure faults and must never be mislabeled as agent
    failures. Parser failures can be supplied through ``submission_error`` by a
    transport such as the CLI after it hashes the exact submitted bytes.
    """
    item_weight, family_weight, invalid_score = _protocol_scoring(protocol)
    instances, ids = _validate_family(family, item_weight, family_weight)
    evaluator_sha256 = _evaluator_sha256()
    projection_values = (agent_projection_sha256, agent_binding_sha256)
    if (projection_values[0] is None) != (projection_values[1] is None):
        raise ValueError("agent projection and binding hashes must be supplied together")
    if any(
        value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in projection_values
    ):
        raise ValueError("agent projection and binding hashes must be lowercase SHA-256 values")

    def invalid(reason: str, digest: str | None) -> dict[str, Any]:
        results = [
            {
                "instance_id": identity,
                "correct": False,
                "schema_compliant": False,
                "reason": "submission rejected before instance validation",
            }
            for identity in ids
        ]
        return _receipt(
            family=family,
            protocol=protocol,
            submission_sha256=digest,
            evaluator_sha256=evaluator_sha256,
            item_weight=item_weight,
            family_weight=family_weight,
            results=results,
            invalid_submission=True,
            invalid_reason=reason,
            invalid_score=invalid_score,
            agent_projection_sha256=agent_projection_sha256,
            agent_binding_sha256=agent_binding_sha256,
        )

    if submission_error is not None:
        if not isinstance(submission_error, str) or not submission_error:
            raise ValueError("submission_error must be a non-empty string")
        return invalid(f"submission parse error: {submission_error}", submission_sha256)
    if not isinstance(submissions, list):
        return invalid("submission must be a list of JSON objects", submission_sha256)
    if submission_sha256 is None:
        try:
            submission_sha256 = canonical_sha256(submissions)
        except (TypeError, ValueError) as error:
            return invalid(f"submission is not canonical JSON: {error}", None)

    by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(submissions, 1):
        if not isinstance(row, dict):
            return invalid(f"submission row {index} is not an object", submission_sha256)
        identity = row.get("instance_id")
        if not isinstance(identity, str) or not identity:
            return invalid(f"submission row {index} lacks instance_id", submission_sha256)
        if identity in by_id:
            return invalid(f"duplicate instance_id: {identity}", submission_sha256)
        if identity not in ids:
            return invalid(f"unknown instance_id: {identity}", submission_sha256)
        by_id[identity] = row

    results = []
    for instance in instances:
        row = by_id.get(instance["id"], {})
        validator = VALIDATORS[instance["validator"]]
        outcome = validator(instance, row)
        results.append({"instance_id": instance["id"], **outcome.to_dict()})

    return _receipt(
        family=family,
        protocol=protocol,
        submission_sha256=submission_sha256,
        evaluator_sha256=evaluator_sha256,
        item_weight=item_weight,
        family_weight=family_weight,
        results=results,
        invalid_submission=False,
        invalid_reason=None,
        invalid_score=invalid_score,
        agent_projection_sha256=agent_projection_sha256,
        agent_binding_sha256=agent_binding_sha256,
    )
