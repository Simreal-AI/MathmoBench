from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchcore import atomic_json, file_sha256, load_json, load_jsonl
from .grading import grade_family
from .projection import translate_agent_submissions


_SOURCE_TREE_PROTOCOL = Path(__file__).resolve().parents[2] / "configs/protocol.json"
# Byte-identical copy shipped inside the wheel; tests enforce equality with
# configs/protocol.json, which remains the single source of truth.
_PACKAGED_PROTOCOL = Path(__file__).resolve().with_name("protocol.json")


def default_protocol_path() -> Path:
    """Prefer the repository's frozen protocol; fall back to the packaged copy."""
    return _SOURCE_TREE_PROTOCOL if _SOURCE_TREE_PROTOCOL.is_file() else _PACKAGED_PROTOCOL


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade one constraint-shift math family")
    parser.add_argument("family")
    parser.add_argument("submission")
    parser.add_argument("--protocol", help="frozen protocol JSON (default: configs/protocol.json)")
    parser.add_argument(
        "--binding",
        help="evaluator-only binding for a submission that uses opaque agent-view IDs",
    )
    parser.add_argument("--output")
    args = parser.parse_args()
    family = load_json(args.family)
    protocol = load_json(args.protocol or default_protocol_path())
    binding = load_json(args.binding) if args.binding else None
    submission_sha256 = file_sha256(args.submission)
    try:
        submissions = load_jsonl(args.submission, id_field="instance_id")
    except ValueError as error:
        if binding is not None:
            # Validate evaluator-owned state even when candidate JSON is bad.
            translate_agent_submissions(binding, family, [])
        result = grade_family(
            family,
            [],
            protocol,
            submission_error=f"{type(error).__name__}: {error}",
            submission_sha256=submission_sha256,
            agent_projection_sha256=(
                binding["agent_projection_sha256"] if binding is not None else None
            ),
            agent_binding_sha256=(binding["binding_sha256"] if binding is not None else None),
        )
    else:
        if binding is not None:
            submissions = translate_agent_submissions(binding, family, submissions)
        result = grade_family(
            family,
            submissions,
            protocol,
            submission_sha256=submission_sha256,
            agent_projection_sha256=(
                binding["agent_projection_sha256"] if binding is not None else None
            ),
            agent_binding_sha256=(binding["binding_sha256"] if binding is not None else None),
        )
    if args.output:
        atomic_json(Path(args.output), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
