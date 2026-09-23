from __future__ import annotations

import argparse
import json

from benchcore import atomic_json
from .generators import DEFAULT_SIZE, MAX_SIZE, MIN_SIZE, build_matching_family
from .generators_constraints import BUILDERS


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a deterministic constraint-shift math family")
    parser.add_argument("--template", choices=["matching", *sorted(BUILDERS)], default="matching")
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--size",
        type=int,
        help=f"vertices per side for the seeded matching template ({MIN_SIZE}-{MAX_SIZE}, default {DEFAULT_SIZE})",
    )
    parser.add_argument("--family-id")
    parser.add_argument("--track")
    parser.add_argument("--disclose-seed", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.template == "matching":
        if args.seed is None:
            parser.error("--seed is required for the matching template")
        try:
            family = build_matching_family(
                args.seed,
                size=args.size,
                family_id=args.family_id,
                track=args.track or "fresh_private",
                disclose_seed=args.disclose_seed,
            )
        except ValueError as error:
            parser.error(str(error))
    else:
        if (
            args.seed is not None
            or args.size is not None
            or args.family_id
            or args.track not in {None, "public_dev"}
            or args.disclose_seed
        ):
            parser.error("fixed public templates accept only --template, --track public_dev, and --output")
        family = BUILDERS[args.template]()
    atomic_json(args.output, family)
    print(json.dumps({"family_id": family["family_id"], "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
