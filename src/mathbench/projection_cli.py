from __future__ import annotations

import argparse
import json

from benchcore import load_json
from .projection import export_family_projection


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a shuffled, opaque-ID Math agent view and evaluator-only binding"
    )
    parser.add_argument("family", help="operator family.json")
    parser.add_argument("--agent-view", required=True, help="agent-visible JSON output")
    parser.add_argument("--binding", required=True, help="evaluator-only binding JSON output")
    randomization = parser.add_mutually_exclusive_group(required=True)
    randomization.add_argument(
        "--seed",
        type=int,
        help="reproducible smoke-test randomization; do not use a guessable seed for scored runs",
    )
    randomization.add_argument(
        "--salt",
        help="high-entropy evaluator secret for a scored run",
    )
    args = parser.parse_args()

    agent_view, binding = export_family_projection(
        load_json(args.family),
        args.agent_view,
        args.binding,
        seed=args.seed,
        salt=args.salt,
    )
    print(
        json.dumps(
            {
                "agent_view": args.agent_view,
                "binding": args.binding,
                "projection_id": agent_view["projection_id"],
                "projection_sha256": binding["agent_projection_sha256"],
                "binding_sha256": binding["binding_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
