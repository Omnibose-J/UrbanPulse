"""Print a re-judge table. `python -m engine rejudge` does not change the flag file."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from engine import db, settings
from engine.judge import boot, reset_rng, state_for, verdict, worse
from engine.log import log
from engine.parsers import KST

JOB = "rejudge"
BARS = {"lively": 85.0, "crowd": 80.0, "avoid": 60.0}


def run(apply: bool = False, flags_path: Path | None = None) -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    path = flags_path or Path(__file__).resolve().parents[1] / "config" / "feature_flags.yaml"
    before = path.read_bytes()
    reset_rng()
    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
        table, strip, changes = _judge(conn)
    today = datetime.now(KST).date()
    out = settings.REPO_ROOT / "data" / "rejudge" / f"{today.isoformat()}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_proposed_text(path, changes, today), encoding="utf-8")
    for line in table:
        print(line)
    detail = {
        "table": table,
        "strip": strip,
        "changes": changes,
        "yaml": str(out.relative_to(settings.REPO_ROOT)),
    }
    if apply and changes:
        path.write_text(_proposed_text(path, changes, today), encoding="utf-8")
    elif path.read_bytes() != before:
        path.write_bytes(before)
        return 1
    log(JOB, "done", changes=len(changes))
    _record(env["DATABASE_URL"], detail)
    return 0


def _judge(conn) -> tuple[list[str], list[str], dict[tuple[str, str, str], str]]:
    reco = pd.read_sql_query(
        """
        select r.place_id, r.date, r.purpose, r.tolerance, r.n_hours, r.n_lively, r.n_crowd_ok,
               p.foreign_heavy, h.kind
        from reco_eval_daily r
        join places p on p.id = r.place_id
        left join holidays h on h.date = r.date
        """,
        conn,
    )
    if not reco.empty:
        reco = reco[~reco["kind"].isin(["seol", "chuseok"])]
    lines = []
    changes = {}
    for group, foreign in (("a1", False), ("a1_foreign", True)):
        part = reco[reco["foreign_heavy"] == foreign] if not reco.empty else reco
        for purpose in ("sight", "food", "shop"):
            for tolerance in ("calm", "moderate", "busy_ok"):
                combo = _combo(part, purpose, tolerance) if not part.empty else part
                label = f"{group} {purpose} {tolerance}"
                if combo.empty or combo["date"].nunique() < 28 or combo["place_id"].nunique() < 10:
                    lines.append(f"{label} insufficient")
                    continue
                lively = _rate(combo, "n_lively", "n_hours")
                result = verdict(label + " lively", lively["point"], lively["ci"], BARS["lively"])
                if tolerance != "busy_ok":
                    crowd = _rate(combo, "n_crowd_ok", "n_hours")
                    crowd_result = verdict(label + " crowd", crowd["point"], crowd["ci"], BARS["crowd"])
                    result = worse(result, crowd_result)
                state = state_for(result)
                lines.append(f"{label} {result} {state}")
                changes[(group, purpose, tolerance)] = state
    strip_lines = _strip(conn)
    return lines, strip_lines, changes


def _combo(frame: pd.DataFrame, purpose: str, tolerance: str) -> pd.DataFrame:
    return frame[(frame["purpose"] == purpose) & (frame["tolerance"] == tolerance)]


def _rate(frame: pd.DataFrame, numer: str, denom: str) -> dict:
    point = float(frame[numer].sum()) / float(frame[denom].sum()) * 100
    groups = {}
    for place, part in frame.groupby("place_id"):
        groups[place] = np.array([float(part[numer].sum()) / float(part[denom].sum())])
    return {"point": point, "ci": boot(groups, lambda samples: np.concatenate(samples).mean() * 100)}


def _strip(conn) -> list[str]:
    frame = pd.read_sql_query(
        """
        select s.place_id, s.date, s.purpose, s.tolerance, s.n_ok, s.n_ok_lively, s.n_ok_crowd_ok,
               s.n_avoid, s.n_avoid_unfit, p.foreign_heavy, h.kind
        from strip_eval_daily s
        join places p on p.id = s.place_id
        left join holidays h on h.date = s.date
        """,
        conn,
    )
    if frame.empty:
        return []
    frame = frame[~frame["kind"].isin(["seol", "chuseok"])]
    lines = []
    for foreign, group in ((False, "a1"), (True, "a1_foreign")):
        part = frame[frame["foreign_heavy"] == foreign]
        for purpose in ("sight", "food", "shop"):
            for tolerance in ("calm", "moderate", "busy_ok"):
                combo = _combo(part, purpose, tolerance)
                label = f"strip {group} {purpose} {tolerance}"
                if combo.empty or combo["date"].nunique() < 28 or combo["place_id"].nunique() < 10:
                    lines.append(f"{label} insufficient")
    return lines


def _proposed_text(path: Path, changes: dict, today: date) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if line.startswith("judged_at:"):
            out.append(f'judged_at: "{today.isoformat()}"')
            continue
        replaced = line
        for (group, purpose, tolerance), state in changes.items():
            needle = f"group: {group}, purpose: {purpose}, tolerance: {tolerance},"
            if needle in line:
                replaced = line
                for old in ("on", "reference", "off"):
                    token = f"state: {old}"
                    if token in replaced:
                        replaced = replaced.replace(token, f"state: {state}", 1)
                        break
        out.append(replaced)
    return "\n".join(out) + "\n"


def _record(url: str, detail: dict) -> None:
    from psycopg.types.json import Jsonb

    with db.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into job_runs (job, status, finished_at, detail)
                values ('rejudge', 'ok', now(), %s)
                """,
                (Jsonb(detail),),
            )
        conn.commit()
