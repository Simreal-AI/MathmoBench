from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
from pathlib import Path
import re
from typing import Any

from benchcore import atomic_json, canonical_sha256


PROJECTION_SCHEMA_VERSION = 1
_DOMAIN = b"constraint-shift-math-agent-view-v1"
_FORBIDDEN_FIELD_FRAGMENTS = frozenset(
    {"variant", "validator", "generator", "title", "track", "scoring", "reference"}
)
_FORBIDDEN_HINT = re.compile(
    r"\b(?:feasible|infeasible|feasibility|boundary|critical|non[-_\s]?critical)\b",
    re.IGNORECASE,
)

AGENT_VIEW_FIELDS = frozenset(
    {"schema_version", "benchmark", "projection_id", "response_format", "goal_contracts", "instances"}
)
AGENT_INSTANCE_FIELDS = frozenset({"id", "goal", "statement", "input"})
_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "benchmark",
        "visibility",
        "operator_family_id",
        "operator_family_sha256",
        "agent_projection_id",
        "agent_projection_sha256",
        "randomization_kind",
        "randomization_commitment_sha256",
        "instance_bindings",
        "binding_sha256",
    }
)
_BINDING_ROW_FIELDS = frozenset(
    {"operator_instance_id", "agent_instance_id", "operator_instance_sha256"}
)

_NEUTRAL_STATEMENTS = {
    "classify_perfect_matching": (
        "Decide whether the bipartite graph admits a perfect matching. Return a matching witness "
        "when it does, or a Hall-subset obstruction when it does not."
    ),
    "maximum_matching": (
        "Return a maximum matching and an equal-size minimum vertex cover."
    ),
    "classify_exact_subset": (
        "Decide whether an indexed subset sums exactly to the target. Return selected zero-based "
        "indices when it does, or a common-divisor or superincreasing-greedy certificate when it does not."
    ),
    "closest_subset": (
        "Return zero-based indices for a subset minimizing absolute distance from the target, "
        "together with a common-divisor or superincreasing-greedy lower-bound certificate."
    ),
    "classify_k_coloring": (
        "Decide whether the graph admits a coloring using at most k colors. Return a vertex-to-color "
        "map when it does, or a clique, odd-cycle, or odd-wheel obstruction when it does not."
    ),
    "minimum_coloring": (
        "Return a minimum coloring and a structural lower-bound certificate of the same size."
    ),
    "classify_bin_limit": (
        "Decide whether all indexed items fit in at most bin_limit bins. Return bins of zero-based "
        "item indices when they do, or a total-capacity or pairwise-incompatibility lower-bound "
        "certificate when they do not."
    ),
    "minimum_bins": (
        "Return a minimum-bin packing and a total-capacity or pairwise-incompatibility lower-bound "
        "certificate of the same size."
    ),
}

_SUBSET_INFEASIBLE_OBSTRUCTIONS = [
    {"type": "common_divisor", "divisor": "integer greater than 1"},
    {"type": "superincreasing_greedy", "remainder": "positive integer"},
]
_SUBSET_OPTIMAL_OBSTRUCTIONS = [
    {"type": "common_divisor", "divisor": "integer greater than 1"},
    {"type": "superincreasing_greedy", "remainder": "nonnegative integer"},
]

_GOAL_CONTRACTS: dict[str, dict[str, Any]] = {
    "classify_perfect_matching": {
        "verdicts": {
            "feasible": {
                "answer": {"matching": [["left vertex", "right vertex"]]},
                "certificate": {},
            },
            "infeasible": {
                "answer": {},
                "certificate": {"hall_subset": ["left vertex"]},
            },
        },
        "additional_fields": False,
    },
    "maximum_matching": {
        "verdicts": {
            "optimal": {
                "answer": {"matching": [["left vertex", "right vertex"]]},
                "certificate": {
                    "minimum_vertex_cover": {
                        "left": ["left vertex"],
                        "right": ["right vertex"],
                    }
                },
            }
        },
        "additional_fields": False,
    },
    "classify_exact_subset": {
        "verdicts": {
            "feasible": {"answer": {"indices": ["zero-based integer"]}, "certificate": {}},
            "infeasible": {
                "answer": {},
                "certificate_one_of": deepcopy(_SUBSET_INFEASIBLE_OBSTRUCTIONS),
            },
        },
        "additional_fields": False,
    },
    "closest_subset": {
        "verdicts": {
            "optimal": {
                "answer": {
                    "indices": ["zero-based integer"],
                    "distance": "nonnegative integer",
                },
                "certificate_one_of": deepcopy(_SUBSET_OPTIMAL_OBSTRUCTIONS),
            }
        },
        "additional_fields": False,
    },
    "classify_k_coloring": {
        "verdicts": {
            "feasible": {
                "answer": {"coloring": {"vertex": "integer in 1..k"}},
                "certificate": {},
            },
            "infeasible": {
                "answer": {},
                "certificate_one_of": [
                    {"type": "clique", "vertices": ["vertex"]},
                    {"type": "odd_cycle", "cycle": ["cyclically ordered vertex"]},
                    {
                        "type": "odd_wheel",
                        "hub": "vertex",
                        "rim": ["cyclically ordered vertex"],
                    },
                ],
            },
        },
        "additional_fields": False,
    },
    "minimum_coloring": {
        "verdicts": {
            "optimal": {
                "answer": {
                    "coloring": {"vertex": "positive integer"},
                    "colors_used": "positive integer",
                },
                "certificate_one_of": [
                    {"type": "clique", "vertices": ["vertex"]},
                    {"type": "odd_cycle", "cycle": ["cyclically ordered vertex"]},
                    {
                        "type": "odd_wheel",
                        "hub": "vertex",
                        "rim": ["cyclically ordered vertex"],
                    },
                ],
            }
        },
        "additional_fields": False,
    },
    "classify_bin_limit": {
        "verdicts": {
            "feasible": {
                "answer": {"bins": [["zero-based item index"]]},
                "certificate": {},
            },
            "infeasible": {
                "answer": {},
                "certificate_one_of": [
                    {"type": "total_capacity"},
                    {"type": "incompatible_items", "indices": ["zero-based item index"]},
                ],
            },
        },
        "additional_fields": False,
    },
    "minimum_bins": {
        "verdicts": {
            "optimal": {
                "answer": {
                    "bins": [["zero-based item index"]],
                    "bin_count": "positive integer",
                },
                "certificate_one_of": [
                    {"type": "total_capacity"},
                    {"type": "incompatible_items", "indices": ["zero-based item index"]},
                ],
            }
        },
        "additional_fields": False,
    },
}


def _randomization_material(*, seed: int | None, salt: str | None) -> tuple[str, bytes]:
    if (seed is None) == (salt is None):
        raise ValueError("provide exactly one of seed or salt")
    if seed is not None:
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("seed must be an integer in [0, 2**63)")
        return "seed", str(seed).encode("ascii")
    if not isinstance(salt, str) or not salt:
        raise ValueError("salt must be a non-empty string")
    return "salt", salt.encode("utf-8")


def _keyed_digest(secret: bytes, label: str, *parts: str) -> bytes:
    message = b"\0".join([label.encode("ascii"), *(part.encode("utf-8") for part in parts)])
    return hmac.new(secret, message, hashlib.sha256).digest()


def _opaque_id(secret: bytes, label: str, family_hash: str, internal_id: str) -> str:
    value = int.from_bytes(_keyed_digest(secret, label, family_hash, internal_id)[:16], "big")
    prefix = "p" if label == "projection-id" else "q"
    return f"{prefix}_{value:039d}"


def _contains_forbidden_field(key: str) -> bool:
    lowered = key.casefold()
    return any(fragment in lowered for fragment in _FORBIDDEN_FIELD_FRAGMENTS)


def _assert_public_safe(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"public projection key is not a string at {path}")
            if _contains_forbidden_field(key):
                raise ValueError(f"forbidden public field at {path}.{key}")
            _assert_public_safe(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_public_safe(child, f"{path}[{index}]")


def _assert_no_answer_hints(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_no_answer_hints(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_answer_hints(child, f"{path}[{index}]")
        return
    if isinstance(value, str) and _FORBIDDEN_HINT.search(value):
        raise ValueError(f"answer-revealing term in public task content at {path}")


def _public_instance(instance: dict[str, Any], public_id: str) -> dict[str, Any]:
    return {
        "id": public_id,
        "goal": instance["goal"],
        "statement": _NEUTRAL_STATEMENTS[instance["goal"]],
        "input": deepcopy(instance["input"]),
    }


def _assemble_agent_view(
    projection_id: str,
    public_instances: list[dict[str, Any]],
) -> dict[str, Any]:
    goals = sorted({instance["goal"] for instance in public_instances})
    agent_view = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "benchmark": "constraint-shift-math",
        "projection_id": projection_id,
        "response_format": {
            "encoding": "jsonl",
            "one_record_per_instance": True,
            "instance_id_source": "copy the instance.id value",
            "goal_contract_source": "use the contract keyed by instance.goal",
            "required_fields": ["instance_id", "verdict", "answer", "certificate"],
            "additional_fields": False,
        },
        "goal_contracts": {goal: deepcopy(_GOAL_CONTRACTS[goal]) for goal in goals},
        "instances": public_instances,
    }
    if set(agent_view) != AGENT_VIEW_FIELDS:
        raise RuntimeError("agent-view whitelist drift")
    if any(set(instance) != AGENT_INSTANCE_FIELDS for instance in agent_view["instances"]):
        raise RuntimeError("agent-instance whitelist drift")
    _assert_public_safe(agent_view)
    _assert_no_answer_hints(agent_view["instances"], "$.instances")
    return agent_view


def _validate_operator_family(family: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(family, dict):
        raise ValueError("operator family must be an object")
    if family.get("benchmark") != "constraint-shift-math":
        raise ValueError("operator family has an unexpected benchmark")
    family_id = family.get("family_id")
    instances = family.get("instances")
    if family.get("track") not in {"public_dev", "static_hidden", "fresh_private", "retired"}:
        raise ValueError("operator family has an unknown track")
    if not isinstance(family_id, str) or not family_id:
        raise ValueError("operator family needs a non-empty family_id")
    if not isinstance(instances, list) or not instances:
        raise ValueError("operator family needs a non-empty instances list")
    internal_ids: list[str] = []
    for index, instance in enumerate(instances):
        if not isinstance(instance, dict):
            raise ValueError(f"operator instance {index} is not an object")
        internal_id = instance.get("id")
        goal = instance.get("goal")
        task_input = instance.get("input")
        if not isinstance(internal_id, str) or not internal_id:
            raise ValueError(f"operator instance {index} lacks a non-empty id")
        if goal not in _NEUTRAL_STATEMENTS:
            raise ValueError(f"operator instance {internal_id} has an unsupported goal")
        if not isinstance(task_input, dict):
            raise ValueError(f"operator instance {internal_id} input must be an object")
        canonical_sha256(task_input)
        internal_ids.append(internal_id)
    if len(internal_ids) != len(set(internal_ids)):
        raise ValueError("operator instance IDs must be unique")
    canonical_sha256(family)
    return family_id, instances


def project_family(
    family: dict[str, Any],
    *,
    seed: int | None = None,
    salt: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an agent-safe family view and its evaluator-only identity binding.

    The public object is assembled from an explicit whitelist. Source statements
    are intentionally ignored: every supported goal receives a neutral prompt.
    The seed or salt affects both ordering and opaque identifiers, but neither
    value is serialized into the public view or evaluator binding.
    """

    family_id, instances = _validate_operator_family(family)
    if family.get("track") in {"static_hidden", "fresh_private"}:
        if seed is not None:
            raise ValueError("scored private tracks require --salt rather than a numeric seed")
        if not isinstance(salt, str) or len(salt.encode("utf-8")) < 32:
            raise ValueError("scored private tracks require at least 32 bytes of secret salt")
    randomization_kind, material = _randomization_material(seed=seed, salt=salt)
    family_hash = canonical_sha256(family)
    secret = hashlib.sha256(_DOMAIN + b"\0" + randomization_kind.encode("ascii") + b"\0" + material).digest()

    projected_rows: list[tuple[bytes, dict[str, Any], dict[str, Any]]] = []
    public_ids: set[str] = set()
    for instance in instances:
        internal_id = instance["id"]
        public_id = _opaque_id(secret, "instance-id", family_hash, internal_id)
        if public_id in public_ids:
            raise RuntimeError("opaque instance ID collision")
        public_ids.add(public_id)
        public_instance = _public_instance(instance, public_id)
        binding_row = {
            "operator_instance_id": internal_id,
            "agent_instance_id": public_id,
            "operator_instance_sha256": canonical_sha256(instance),
        }
        order_key = _keyed_digest(secret, "instance-order", family_hash, internal_id)
        projected_rows.append((order_key, public_instance, binding_row))

    projected_rows.sort(key=lambda row: (row[0], row[2]["operator_instance_id"]))
    projection_id = _opaque_id(secret, "projection-id", family_hash, family_id)
    agent_view = _assemble_agent_view(projection_id, [row[1] for row in projected_rows])

    projection_hash = canonical_sha256(agent_view)
    binding_core = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "benchmark": "constraint-shift-math",
        "visibility": "evaluator_only",
        "operator_family_id": family_id,
        "operator_family_sha256": family_hash,
        "agent_projection_id": projection_id,
        "agent_projection_sha256": projection_hash,
        "randomization_kind": randomization_kind,
        "randomization_commitment_sha256": hashlib.sha256(secret).hexdigest(),
        "instance_bindings": [row[2] for row in projected_rows],
    }
    binding = {**binding_core, "binding_sha256": canonical_sha256(binding_core)}
    return agent_view, binding


def binding_maps(binding: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Return structurally validated operator-to-agent and reverse ID maps."""

    rows = binding.get("instance_bindings") if isinstance(binding, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("binding needs a non-empty instance_bindings list")
    operator_to_agent: dict[str, str] = {}
    agent_to_operator: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("binding row must be an object")
        if set(row) != _BINDING_ROW_FIELDS:
            raise ValueError("binding row fields differ from the evaluator schema")
        operator_id = row.get("operator_instance_id")
        agent_id = row.get("agent_instance_id")
        if not isinstance(operator_id, str) or not operator_id or not isinstance(agent_id, str) or not agent_id:
            raise ValueError("binding row needs non-empty operator and agent IDs")
        if operator_id in operator_to_agent or agent_id in agent_to_operator:
            raise ValueError("binding IDs must be one-to-one")
        operator_to_agent[operator_id] = agent_id
        agent_to_operator[agent_id] = operator_id
    return operator_to_agent, agent_to_operator


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validated_binding_context(
    binding: dict[str, Any],
    family: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    family_id, instances = _validate_operator_family(family)
    if not isinstance(binding, dict) or set(binding) != _BINDING_FIELDS:
        raise ValueError("binding fields differ from the evaluator schema")
    binding_hash = binding.get("binding_sha256")
    binding_core = {key: value for key, value in binding.items() if key != "binding_sha256"}
    if not _is_sha256(binding_hash) or binding_hash != canonical_sha256(binding_core):
        raise ValueError("binding hash mismatch")
    if (
        binding.get("schema_version") != PROJECTION_SCHEMA_VERSION
        or binding.get("benchmark") != "constraint-shift-math"
        or binding.get("visibility") != "evaluator_only"
    ):
        raise ValueError("binding identity or visibility mismatch")
    family_hash = canonical_sha256(family)
    if binding.get("operator_family_id") != family_id or binding.get("operator_family_sha256") != family_hash:
        raise ValueError("operator family does not match binding")
    projection_id = binding.get("agent_projection_id")
    if not isinstance(projection_id, str) or re.fullmatch(r"p_[0-9]{39}", projection_id) is None:
        raise ValueError("binding has a malformed projection ID")
    if not _is_sha256(binding.get("agent_projection_sha256")):
        raise ValueError("binding has a malformed projection hash")
    if binding.get("randomization_kind") not in {"seed", "salt"} or not _is_sha256(
        binding.get("randomization_commitment_sha256")
    ):
        raise ValueError("binding has malformed randomization metadata")

    operator_to_agent, agent_to_operator = binding_maps(binding)
    by_id = {instance["id"]: instance for instance in instances}
    if set(operator_to_agent) != set(by_id) or len(operator_to_agent) != len(instances):
        raise ValueError("binding does not cover the operator family exactly")

    public_instances: list[dict[str, Any]] = []
    for row in binding["instance_bindings"]:
        operator_id = row["operator_instance_id"]
        agent_id = row["agent_instance_id"]
        if re.fullmatch(r"q_[0-9]{39}", agent_id) is None:
            raise ValueError("binding has a malformed agent instance ID")
        source = by_id[operator_id]
        if not _is_sha256(row["operator_instance_sha256"]) or row["operator_instance_sha256"] != canonical_sha256(source):
            raise ValueError("operator instance hash mismatch")
        public_instances.append(_public_instance(source, agent_id))

    reconstructed = _assemble_agent_view(projection_id, public_instances)
    if canonical_sha256(reconstructed) != binding["agent_projection_sha256"]:
        raise ValueError("agent projection hash mismatch")
    return reconstructed, operator_to_agent, agent_to_operator


def translate_agent_submissions(
    binding: dict[str, Any],
    family: dict[str, Any],
    rows: list[Any],
) -> list[Any]:
    """Map opaque IDs to operator IDs after validating every evaluator binding.

    Candidate-owned mistakes are deliberately not raised here. Unknown or
    malformed public IDs become an impossible sentinel so the grader can record
    a normal zero result. Only evaluator-owned family/binding/hash corruption
    raises an exception.
    """

    _, _, agent_to_operator = _validated_binding_context(binding, family)
    internal_ids = {instance["id"] for instance in family["instances"]}
    translated: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            translated.append(deepcopy(row))
            continue
        converted = deepcopy(row)
        agent_id = converted.get("instance_id")
        if isinstance(agent_id, str) and agent_id in agent_to_operator:
            converted["instance_id"] = agent_to_operator[agent_id]
        else:
            try:
                fingerprint = canonical_sha256({"candidate_instance_id": agent_id})[:24]
            except (TypeError, ValueError):
                fingerprint = hashlib.sha256(type(agent_id).__name__.encode("utf-8")).hexdigest()[:24]
            sentinel = f"__unmapped_agent_instance_{fingerprint}"
            while sentinel in internal_ids:
                sentinel += "_x"
            converted["instance_id"] = sentinel
        translated.append(converted)
    return translated


def export_family_projection(
    family: dict[str, Any],
    agent_view_path: str | Path,
    binding_path: str | Path,
    *,
    seed: int | None = None,
    salt: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Atomically write the agent view and evaluator-only binding as JSON."""

    agent_destination = Path(agent_view_path)
    binding_destination = Path(binding_path)
    if agent_destination.resolve() == binding_destination.resolve():
        raise ValueError("agent view and binding need distinct output paths")
    agent_view, binding = project_family(family, seed=seed, salt=salt)
    atomic_json(agent_destination, agent_view)
    atomic_json(binding_destination, binding)
    return agent_view, binding


__all__ = [
    "AGENT_INSTANCE_FIELDS",
    "AGENT_VIEW_FIELDS",
    "binding_maps",
    "export_family_projection",
    "project_family",
    "translate_agent_submissions",
]
