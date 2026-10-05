"""CLI entry: `python -m engine <job>`.

Jobs that are not implemented yet exit 2 and name the work unit that adds them (build contract §8), so a
scheduler wiring them early fails loudly instead of silently doing nothing.
"""

from __future__ import annotations

import argparse
import sys

from engine.jobs import (
    backfill,
    collect,
    evaluate,
    forecast,
    healthcheck,
    ingest_raw,
    integrity,
    load_places,
    rejudge,
    sync_holidays,
    tier_b,
)

NOT_YET: dict[str, str] = {}

JOBS = {
    "evaluate": evaluate.run,
    "integrity": integrity.run,
    "forecast": forecast.run,
    "rejudge": rejudge.run,
    "healthcheck": healthcheck.run,
    "backfill": backfill.run,
    "collect": collect.run,
    "ingest_raw": ingest_raw.run,
    "load_places": load_places.run,
    "sync_holidays": sync_holidays.run,
    "tier_b": tier_b.run,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine", description="UrbanPulse engine jobs")
    sub = parser.add_subparsers(dest="job", required=True)
    for name in [*NOT_YET, *JOBS]:
        command = sub.add_parser(name)
        if name in ("ingest_raw", "evaluate"):
            command.add_argument("--date", default=None)
        if name == "rejudge":
            command.add_argument("--apply", action="store_true")
        if name == "tier_b":
            command.add_argument("--check", action="store_true")
        if name == "integrity":
            command.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    if args.job in NOT_YET:
        print(f"{args.job}: not implemented until {NOT_YET[args.job]}", file=sys.stderr)
        return 2
    if args.job == "ingest_raw":
        return ingest_raw.run(date=args.date)
    if args.job == "evaluate":
        from datetime import date

        day = date.fromisoformat(args.date) if args.date else None
        return evaluate.run(day)
    if args.job == "rejudge":
        return rejudge.run(apply=args.apply)
    if args.job == "tier_b":
        return tier_b.run(check_only=args.check)
    if args.job == "integrity":
        return integrity.run(full=args.full)
    return JOBS[args.job]()


if __name__ == "__main__":
    sys.exit(main())
