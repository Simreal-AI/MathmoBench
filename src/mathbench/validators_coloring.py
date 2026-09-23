from __future__ import annotations

from typing import Any

from .validators import ValidationResult, _pairs, _string_list


def _graph(instance: dict[str, Any]) -> tuple[list[str], set[tuple[str, str]], int]:
    data = instance.get("input")
    if not isinstance(data, dict) or not _string_list(data.get("vertices")):
        raise ValueError("Coloring input needs a vertex list")
    vertices = data["vertices"]
    if not vertices or len(vertices) != len(set(vertices)):
        raise ValueError("Coloring vertices must be unique")
    vertex_set = set(vertices)
    raw_edges = _pairs(data.get("edges"))
    k = data.get("k")
    if raw_edges is None or type(k) is not int or k <= 0:
        raise ValueError("Coloring input needs edges and a positive k")
    edges: set[tuple[str, str]] = set()
    for left, right in raw_edges:
        if left not in vertex_set or right not in vertex_set or left == right:
            raise ValueError("Coloring edges must join distinct declared vertices")
        edge = tuple(sorted((left, right)))
        if edge in edges:
            raise ValueError("Coloring edges must be unique as undirected pairs")
        edges.add(edge)
    return vertices, edges, k


def _edge(edges: set[tuple[str, str]], left: str, right: str) -> bool:
    return tuple(sorted((left, right))) in edges


def _valid_coloring(value: Any, vertices: list[str], edges: set[tuple[str, str]], limit: int) -> bool:
    if not isinstance(value, dict) or set(value) != set(vertices) or limit <= 0:
        return False
    if any(type(color) is not int or color < 1 or color > limit for color in value.values()):
        return False
    return all(value[left] != value[right] for left, right in edges)


def _certificate_lower_bound(certificate: dict[str, Any], vertices: set[str], edges: set[tuple[str, str]]) -> int | None:
    kind = certificate.get("type")
    if kind == "clique" and set(certificate) == {"type", "vertices"}:
        clique = certificate.get("vertices")
        if not _string_list(clique) or len(clique) != len(set(clique)) or not set(clique) <= vertices:
            return None
        if all(_edge(edges, clique[i], clique[j]) for i in range(len(clique)) for j in range(i + 1, len(clique))):
            return len(clique)
        return None
    if kind == "odd_cycle" and set(certificate) == {"type", "cycle"}:
        cycle = certificate.get("cycle")
        if (
            not _string_list(cycle)
            or len(cycle) < 3
            or len(cycle) % 2 == 0
            or len(cycle) != len(set(cycle))
            or not set(cycle) <= vertices
        ):
            return None
        return 3 if all(_edge(edges, cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))) else None
    if kind == "odd_wheel" and set(certificate) == {"type", "hub", "rim"}:
        hub = certificate.get("hub")
        rim = certificate.get("rim")
        if (
            not isinstance(hub, str)
            or hub not in vertices
            or not _string_list(rim)
            or len(rim) < 3
            or len(rim) % 2 == 0
            or len(rim) != len(set(rim))
            or hub in rim
            or not set(rim) <= vertices
        ):
            return None
        rim_edges = all(_edge(edges, rim[i], rim[(i + 1) % len(rim)]) for i in range(len(rim)))
        spokes = all(_edge(edges, hub, vertex) for vertex in rim)
        return 4 if rim_edges and spokes else None
    return None


def validate_graph_coloring(instance: dict[str, Any], submission: dict[str, Any]) -> ValidationResult:
    required = {"instance_id", "verdict", "answer", "certificate"}
    compliant = set(submission) == required and submission.get("instance_id") == instance.get("id")
    if not compliant:
        return ValidationResult(False, False, "missing required fields or wrong instance_id")
    if not isinstance(submission["answer"], dict) or not isinstance(submission["certificate"], dict):
        return ValidationResult(False, False, "answer and certificate must be objects")

    vertices, edges, k = _graph(instance)
    goal = instance.get("goal")
    verdict = submission.get("verdict")

    if goal == "classify_k_coloring" and verdict == "feasible":
        if set(submission["answer"]) != {"coloring"} or submission["certificate"]:
            return ValidationResult(False, False, "feasible output needs only answer.coloring")
        correct = _valid_coloring(submission["answer"].get("coloring"), vertices, edges, k)
        return ValidationResult(correct, True, "valid k-coloring" if correct else "invalid k-coloring")

    if goal == "classify_k_coloring" and verdict == "infeasible":
        if submission["answer"]:
            return ValidationResult(False, False, "infeasible output must have an empty answer")
        lower_bound = _certificate_lower_bound(submission["certificate"], set(vertices), edges)
        correct = lower_bound is not None and lower_bound > k
        return ValidationResult(correct, True, "certificate proves more than k colors are needed" if correct else "invalid coloring obstruction")

    if goal == "minimum_coloring" and verdict == "optimal":
        if set(submission["answer"]) != {"coloring", "colors_used"}:
            return ValidationResult(False, False, "optimal answer needs coloring and colors_used")
        colors_used = submission["answer"].get("colors_used")
        if type(colors_used) is not int or colors_used <= 0:
            return ValidationResult(False, True, "colors_used must be a positive integer")
        lower_bound = _certificate_lower_bound(submission["certificate"], set(vertices), edges)
        coloring = submission["answer"].get("coloring")
        correct = (
            _valid_coloring(coloring, vertices, edges, colors_used)
            and set(coloring.values()) == set(range(1, colors_used + 1))
            and lower_bound == colors_used
        )
        return ValidationResult(correct, True, "coloring and obstruction meet at the optimum" if correct else "invalid chromatic-number proof")

    return ValidationResult(False, True, "verdict is unsupported for this goal")


VALIDATORS = {"graph_coloring_v1": validate_graph_coloring}
