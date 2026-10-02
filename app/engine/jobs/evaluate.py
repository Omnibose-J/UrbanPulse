"""Score one date of forecast_log and recommendation_log. `python -m engine evaluate`."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from engine import db, settings
from engine.hourly import hourly_frame
from engine.log import log
from engine.parsers import KST

JOB = "evaluate"
ALLOWED = {"calm": 1, "moderate": 2}


def yesterday(now: datetime | None = None) -> date:
    clock = now or datetime.now(KST)
    return clock.astimezone(KST).date() - timedelta(days=1)


def wape(pred: pd.Series, actual: pd.Series) -> float:
    denom = float(actual.sum())
    if denom == 0:
        raise ValueError("actual sum is 0")
    return float((pred - actual).abs().sum()) / denom


def run(day: date | None = None) -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    target = day or yesterday()
    log(JOB, "start", date=target.isoformat())
    try:
        with db.ledger(env["DATABASE_URL"], JOB) as (conn, ctx):
            detail = evaluate_date(conn, target)
            ctx["status"] = "warn" if detail.get("warn") else "ok"
            ctx["detail"] = detail
    except BaseException as exc:
        log(JOB, "fail", reason=type(exc).__name__)
        raise
    log(JOB, "done", status=ctx["status"])
    return 0


def evaluate_date(conn, target: date) -> dict:
    forecasts = _forecasts(conn, target)
    live = _live(conn, target)
    commerce = _commerce(conn, target)
    holidays = _holiday_dates(conn)
    segment = "holiday" if target in holidays else "normal"
    eval_rows = _eval_rows(forecasts, live, target, segment)
    logs = _recommendation_logs(conn, target)
    places = _place_tiers(conn)
    reco_rows, strip_rows, unscored = _reco_rows(logs, places, live, commerce)
    warn, skipped = _warning(conn, target, holidays)
    with conn.cursor() as cur:
        cur.execute("delete from eval_daily where date = %s", (target,))
        cur.execute("delete from reco_eval_daily where date = %s", (target,))
        cur.execute("delete from strip_eval_daily where date = %s", (target,))
        cur.executemany(
            """
            insert into eval_daily (date, horizon_d, segment, wape_model, wape_baseline, n)
            values (%s, %s, %s, %s, %s, %s)
            """,
            eval_rows,
        )
        cur.executemany(
            """
            insert into reco_eval_daily (
              date, place_id, purpose, tolerance, n_hours, n_lively, n_crowd_ok, chance_hours, chance_lively
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            reco_rows,
        )
        cur.executemany(
            """
            insert into strip_eval_daily (
              date, place_id, purpose, tolerance, n_ok, n_ok_lively, n_ok_crowd_ok, n_avoid, n_avoid_unfit
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            strip_rows,
        )
    conn.commit()
    detail = {
        "date": target.isoformat(),
        "eval_daily": len(eval_rows),
        "reco_eval_daily": len(reco_rows),
        "strip_eval_daily": len(strip_rows),
        "unscored": unscored,
    }
    if skipped:
        detail["warn_skipped"] = skipped
    if warn:
        detail["warn"] = warn
    return detail


def _eval_rows(frame: pd.DataFrame, live: pd.DataFrame, target: date, segment: str) -> list[tuple]:
    if frame.empty or live.empty:
        return []
    joined = frame.merge(live, on=["place_id", "hour"], how="inner")
    rows = []
    for horizon, part in joined.groupby("horizon_d"):
        if part.empty or float(part["value"].sum()) == 0:
            continue
        rows.append(
            (
                target,
                int(horizon),
                segment,
                wape(part["pred"], part["value"]) * 100,
                wape(part["baseline"], part["value"]) * 100,
                int(len(part)),
            )
        )
    return rows


def _warning(conn, target: date, holidays: set[date]) -> tuple[list[dict], str | None]:
    start = target - timedelta(days=27)
    frame = _forecasts_between(conn, start, target)
    live = _live_between(conn, start, target)
    if frame.empty or live.empty:
        return [], "fewer than 14 days"
    joined = frame.merge(live, on=["place_id", "hour"], how="inner")
    joined["day"] = joined["hour"].dt.date
    joined = joined[~joined["day"].isin(holidays)]
    if joined["day"].nunique() < 14:
        return [], "fewer than 14 days"
    warn = []
    for horizon, part in joined.groupby("horizon_d"):
        if float(part["value"].sum()) == 0:
            continue
        model = wape(part["pred"], part["value"]) * 100
        baseline = wape(part["baseline"], part["value"]) * 100
        if model > baseline + 0.3:
            warn.append({"horizon_d": int(horizon), "model": round(model, 4), "baseline": round(baseline, 4)})
    return warn, None


def _reco_rows(logs: list[dict], tiers: dict[str, str], live: pd.DataFrame, commerce: pd.DataFrame):
    reco_rows = []
    strip_rows = []
    unscored = 0
    live_index = _index(live)
    for row in logs:
        tier = tiers.get(row["place_id"], "A2")
        cells = row["hours"] or []
        windows = row["windows"] or []
        window_hours = {hour for window in windows for hour in window.get("hours", [])}
        scored = []
        for cell in cells:
            if cell.get("reason") == "outside_hours":
                continue
            actual = _actual(row, cell["h"], tier, live_index, commerce)
            if actual is None:
                continue
            scored.append((cell, actual))
        if row["purpose"] != "none" and windows:
            in_window = [(cell, actual) for cell, actual in scored if cell["h"] in window_hours]
            if in_window:
                reco_rows.append(_reco_tuple(row, in_window, scored))
            else:
                unscored += 1
        if not scored:
            continue
        strip_rows.append(_strip_tuple(row, tier, scored))
    return reco_rows, strip_rows, unscored


def _actual(row, hour, tier, live_index, commerce):
    level = live_index.get((row["place_id"], hour))
    if level is None:
        return None
    if tier != "A1":
        return {"level": level, "lively": None}
    activity = _activity(commerce, row["place_id"], hour, row["purpose"], row.get("p90"))
    if activity is None:
        return None
    return {"level": level, "lively": activity >= 0.5}


def _activity(commerce: pd.DataFrame, place_id: str, hour: int, purpose: str, p90) -> float | None:
    if commerce.empty or p90 in (None, 0):
        return None
    part = commerce[(commerce["place_id"] == place_id) & (commerce["hour"].dt.hour == hour)]
    if part.empty:
        return None
    column = {"sight": "all", "food": "food", "shop": "shop"}.get(purpose)
    if column is None:
        return None
    return float(part[column].mean()) / float(p90)


def _kept(level: int, tolerance: str) -> bool:
    return level <= ALLOWED[tolerance]


def _unfit(tier: str, tolerance: str, actual: dict) -> bool:
    if tolerance == "busy_ok":
        return actual["lively"] is False
    if tier != "A1":
        return not _kept(actual["level"], tolerance)
    return actual["lively"] is False or not _kept(actual["level"], tolerance)


def _reco_tuple(row, in_window, scored):
    if row["tolerance"] == "busy_ok":
        crowd = None
    else:
        crowd = sum(1 for _, actual in in_window if _kept(actual["level"], row["tolerance"]))
    chance = [item for item in scored if 9 <= item[0]["h"] <= 23]
    return (
        row["date"],
        row["place_id"],
        row["purpose"],
        row["tolerance"],
        len(in_window),
        sum(1 for _, actual in in_window if actual["lively"]),
        crowd,
        len(chance),
        sum(1 for _, actual in chance if actual["lively"]),
    )


def _strip_tuple(row, tier, scored):
    ok = [(cell, actual) for cell, actual in scored if cell.get("rating") == 1]
    avoid = [(cell, actual) for cell, actual in scored if cell.get("rating") == 0]
    lively = None if tier != "A1" else sum(1 for _, actual in ok if actual["lively"])
    if row["tolerance"] == "busy_ok":
        crowd = None
    else:
        crowd = sum(1 for _, actual in ok if _kept(actual["level"], row["tolerance"]))
    unfit = sum(1 for _, actual in avoid if _unfit(tier, row["tolerance"], actual))
    return (
        row["date"],
        row["place_id"],
        row["purpose"],
        row["tolerance"],
        len(ok),
        lively,
        crowd,
        len(avoid),
        unfit,
    )


def _index(live: pd.DataFrame) -> dict:
    if live.empty:
        return {}
    indexed = {}
    for row in live.itertuples(index=False):
        if pd.notna(row.level):
            indexed[(row.place_id, int(row.hour.hour))] = int(row.level)
    return indexed


def _forecasts(conn, target: date) -> pd.DataFrame:
    return _forecasts_between(conn, target, target)


def _forecasts_between(conn, start: date, end: date) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(
            """
            select place_id, target_ts, horizon_d, pred, baseline
            from forecast_log
            where (target_ts at time zone 'Asia/Seoul')::date between %s and %s
            """,
            (start, end),
        )
        rows = cur.fetchall()
    frame = pd.DataFrame(rows, columns=["place_id", "target_ts", "horizon_d", "pred", "baseline"])
    if frame.empty:
        return frame
    frame["hour"] = pd.to_datetime(frame["target_ts"], utc=True).dt.tz_convert(KST).dt.floor("h")
    return frame


def _live(conn, target: date) -> pd.DataFrame:
    return _live_between(conn, target, target)


def _live_between(conn, start: date, end: date) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(
            """
            select place_id, ts, (pop_min + pop_max) / 2.0, level
            from live_obs
            where (ts at time zone 'Asia/Seoul')::date between %s and %s
            """,
            (start, end),
        )
        rows = cur.fetchall()
    frame = pd.DataFrame(rows, columns=["place_id", "ts", "value", "level"])
    return hourly_frame(frame, "floor") if not frame.empty else frame


def _commerce(conn, target: date) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(
            """
            select place_id, ts, pay_cnt,
                   coalesce((cat_counts->>'음식·음료')::float8, 0),
                   coalesce((cat_counts->>'유통')::float8, 0)
                     + coalesce((cat_counts->>'패션·뷰티')::float8, 0)
            from commerce_obs
            where (ts at time zone 'Asia/Seoul')::date = %s
            """,
            (target,),
        )
        rows = cur.fetchall()
    frame = pd.DataFrame(rows, columns=["place_id", "ts", "all", "food", "shop"])
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True).dt.tz_convert(KST)
    frame["hour"] = frame["ts"].dt.floor("h")
    return frame.groupby(["place_id", "hour"], as_index=False)[["all", "food", "shop"]].mean()


def _holiday_dates(conn) -> set[date]:
    with conn.cursor() as cur:
        cur.execute("select date from holidays")
        return {row[0] for row in cur.fetchall()}


def _place_tiers(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("select id, tier from places")
        return {row[0]: row[1] for row in cur.fetchall()}


def _recommendation_logs(conn, target: date) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select place_id, date, tolerance, purpose, windows, hours, p90
            from recommendation_log
            where date = %s
            """,
            (target,),
        )
        columns = ["place_id", "date", "tolerance", "purpose", "windows", "hours", "p90"]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
