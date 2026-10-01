"""CLI entry: `python -m engine <job>`.

Jobs that are not implemented yet exit 2 and name the work unit that adds them (build contract §8), so a
scheduler wiring them early fails loudly instead of silently doing nothing.
"""

from __future__ import annotations

import argparse
import sys

from engine.jobs import backfill, collect, forecast, healthcheck, ingest_raw, load_places, sync_holidays

NOT_YET = {
    "tier_b": "W9",
    "evaluate": "W12",
    "archive": "W12",
}

JOBS = {
    "forecast": forecast.run,
    "healthcheck": healthcheck.run,
    "backfill": backfill.run,
    "collect": collect.run,
    "ingest_raw": ingest_raw.run,
    "load_places": load_places.run,
    "sync_holidays": sync_holidays.run,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine", description="UrbanPulse engine jobs")
    sub = parser.add_subparsers(dest="job", required=True)
    for name in [*NOT_YET, *JOBS]:
        command = sub.add_parser(name)
        if name == "ingest_raw":
            command.add_argument("--date", default=None)
    args = parser.parse_args(argv)
    if args.job in NOT_YET:
        print(f"{args.job}: not implemented until {NOT_YET[args.job]}", file=sys.stderr)
        return 2
    if args.job == "ingest_raw":
        return ingest_raw.run(date=args.date)
    return JOBS[args.job]()


if __name__ == "__main__":
    sys.exit(main())
