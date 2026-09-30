"""CLI entry: `python -m engine <job>`.

Jobs that are not implemented yet exit 2 and name the work unit that adds them (build contract §8), so a
scheduler wiring them early fails loudly instead of silently doing nothing.
"""

from __future__ import annotations

import argparse
import sys

from engine.jobs import healthcheck, load_places

NOT_YET = {
    "backfill": "W3a",
    "collect": "W3",
    "forecast": "W7",
    "tier_b": "W9",
    "evaluate": "W12",
    "archive": "W12",
}

JOBS = {
    "healthcheck": healthcheck.run,
    "load_places": load_places.run,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine", description="UrbanPulse engine jobs")
    sub = parser.add_subparsers(dest="job", required=True)
    for name in [*NOT_YET, *JOBS]:
        sub.add_parser(name)
    args = parser.parse_args(argv)
    if args.job in NOT_YET:
        print(f"{args.job}: not implemented until {NOT_YET[args.job]}", file=sys.stderr)
        return 2
    return JOBS[args.job]()


if __name__ == "__main__":
    sys.exit(main())
