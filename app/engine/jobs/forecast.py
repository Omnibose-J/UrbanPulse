"""Daily forecast. `python -m engine forecast`.

Refreshes place state, thresholds and activity profiles, then writes today's 8-day
`forecast_hourly` rows and an append-only `forecast_log`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd
from psycopg.types.json import Jsonb

from engine import db, settings
from engine.calendar_feats import day_type
from engine.hourly import baseline, hourly_frame
from engine.levels import level_of, thresholds_for
from engine.lively import hourly_commerce, profile_rows
from engine.log import log
from engine.parsers import KST
from engine.ratio_model import load

JOB = "forecast"


def next_place_state(recent_commerce, recent_live, live_days, in_index, threshold_ready) -> tuple[str, str]:
    """Tier and serve_state after a refresh. Experimental rows are not passed in."""
    new_tier = "A1" if recent_commerce else "A2"
    if not recent_live:
        new_state = "off"
    elif in_index and threshold_ready and live_days >= 14:
        new_state = "on"
    else:
        new_state = "preparing"
    return new_tier, new_state


def served_source(in_index: bool, horizon: int, passing: set[int]) -> str:
    if in_index and horizon in passing:
        return "model"
    return "profile"


def served_pop(baseline_value: float, source: str, log_ratio: float) -> float:
    if source == "model":
        return baseline_value * math.exp(log_ratio)
    return baseline_value


def activity_for(tier: str, stored: tuple) -> tuple:
    """A2 rows carry no activity profile."""
    if tier != "A1":
        return (None, None, None)
    return stored


def _today(now: datetime):
    return now.astimezone(KST).date()


def apply_overlay(conn, now: datetime) -> None:
    """Hours with a live observation become `live`; later hours covered by city_fcst become `seoul`."""
    with conn.cursor() as cur:
        cur.execute("set time zone 'Asia/Seoul'")
        cur.execute(
            """
            select place_id, ts, (pop_min + pop_max) / 2.0, level
            from live_obs
            where ts >= date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'
            """
        )
        live_rows = pd.DataFrame(cur.fetchall(), columns=["place_id", "ts", "value", "level"])
        cur.execute(
            """
            select place_id, target_ts, (pop_min + pop_max) / 2.0, level
            from city_fcst
            where target_ts >= date_trunc('hour', now())
            """
        )
        city_rows = cur.fetchall()
    if not live_rows.empty:
        hourly = hourly_frame(live_rows, "floor")
        with conn.cursor() as cur:
            for row in hourly.itertuples(index=False):
                cur.execute(
                    """
                    update forecast_hourly
                    set source = 'live', pop = %s, level = %s, ready = true, stale = false
                    where place_id = %s and target_ts = %s
                    """,
                    (
                        float(row.value),
                        int(row.level) if pd.notna(row.level) else None,
                        row.place_id,
                        row.hour.to_pydatetime(),
                    ),
                )
    if city_rows:
        with conn.cursor() as cur:
            for place_id, target, pop, level in city_rows:
                cur.execute(
                    """
                    update forecast_hourly
                    set source = 'seoul', pop = %s, level = %s, ready = true
                    where place_id = %s and target_ts = %s and source <> 'live'
                    """,
                    (float(pop), int(level), place_id, target),
                )


def _active_model(conn):
    root = settings.REPO_ROOT / "models" / "ratio_v1"
    if not (root / "meta.json").exists():
        return None, []
    model = load(root)
    with conn.cursor() as cur:
        cur.execute(
            """
            select horizons from model_registry
            where name = 'ratio_v1' and active
            order by created_at desc
            limit 1
            """
        )
        row = cur.fetchone()
    passing = list(row[0]) if row and row[0] else []
    return model, passing


def run() -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    started = datetime.now(KST)
    today = _today(started)
    log(JOB, "start", issued=today.isoformat())
    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            cur.execute(
                """
                insert into job_runs (job, status) values ('forecast', 'running') returning id
                """
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        try:
            detail = _build(conn, started, today)
            status = "ok"
        except Exception as exc:
            status = "fail"
            detail = {"error": f"{type(exc).__name__}: {exc}"}
            log(JOB, "fail", reason=detail["error"])
            with conn.cursor() as cur:
                cur.execute(
                    "update job_runs set finished_at = now(), status = %s, detail = %s where id = %s",
                    (status, Jsonb(detail), run_id),
                )
            conn.commit()
            return 1
        with conn.cursor() as cur:
            cur.execute(
                "update job_runs set finished_at = now(), status = %s, detail = %s where id = %s",
                (status, Jsonb(detail), run_id),
            )
        conn.commit()
    log(JOB, "done", places=detail.get("places"), transitions=len(detail.get("transitions", {})))
    return 0


def _build(conn, started: datetime, today) -> dict:
    model, passing = _active_model(conn)
    place_index = set(model.place_index) if model else set()
    version = model.meta["created_at"] if model else "none"
    window_start = datetime.combine(today - timedelta(days=90), datetime.min.time()).replace(tzinfo=KST)
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)
    commerce_since = datetime.combine(today - timedelta(days=28), datetime.min.time()).replace(tzinfo=KST)
    live_since = datetime.combine(today - timedelta(days=7), datetime.min.time()).replace(tzinfo=KST)
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, tier, serve_state from places
            where tier in ('A1', 'A2') and serve_state <> 'experimental'
            """
        )
        places = cur.fetchall()
        cur.execute(
            """
            select p.id,
              exists (
                select 1 from commerce_obs c
                where c.place_id = p.id and c.ts >= %s
              ),
              exists (
                select 1 from live_obs l
                where l.place_id = p.id and l.ts >= %s
              ),
              (
                select count(distinct (l.ts at time zone 'Asia/Seoul')::date)
                from live_obs l where l.place_id = p.id
              )
            from places p
            where p.tier in ('A1', 'A2') and p.serve_state <> 'experimental'
            """,
            (commerce_since, live_since),
        )
        flags = {row[0]: row[1:] for row in cur.fetchall()}
        cur.execute(
            """
            select place_id, ts, (pop_min + pop_max) / 2.0, level
            from live_obs
            where ts >= %s and ts < %s
            """,
            (window_start, today_start),
        )
        window = pd.DataFrame(cur.fetchall(), columns=["place_id", "ts", "value", "level"])
    ready_ids = set()
    threshold_rows = []
    if not window.empty:
        for place_id, part in window.groupby("place_id"):
            t1, t2, t3, days, ready = thresholds_for(part)
            if ready and t1 <= t2 <= t3:
                ready_ids.add(place_id)
            if t1 <= t2 <= t3:
                threshold_rows.append((place_id, t1, t2, t3, days))
    transitions = {}
    with conn.cursor() as cur:
        for place_id, tier, state in places:
            recent_commerce, recent_live, live_days = flags.get(place_id, (False, False, 0))
            new_tier, new_state = next_place_state(
                bool(recent_commerce),
                bool(recent_live),
                int(live_days or 0),
                place_id in place_index,
                place_id in ready_ids,
            )
            if new_tier != tier or new_state != state:
                transitions[place_id] = [state, new_state]
                cur.execute(
                    """
                    update places
                    set tier = %s, serve_state = %s, updated_at = now()
                    where id = %s
                    """,
                    (new_tier, new_state, place_id),
                )
        cur.execute("delete from level_thresholds")
        for row in threshold_rows:
            cur.execute(
                """
                insert into level_thresholds (place_id, t1, t2, t3, based_on_days)
                values (%s, %s, %s, %s, %s)
                """,
                row,
            )
    conn.commit()
    _write_profiles(conn, today)
    _write_forecasts(conn, started, today, model, set(passing), version, ready_ids)
    with conn.cursor() as cur:
        cur.execute(
            """
            delete from forecast_hourly
            where target_ts < (date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul')
            """
        )
    conn.commit()
    return {"transitions": transitions, "places": len(places), "passing_horizons": list(passing)}

def _write_profiles(conn, today) -> None:
    with conn.cursor() as cur:
        cur.execute("select date, kind from holidays")
        kinds = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            """
            select c.place_id, c.ts, c.pay_cnt,
                   coalesce((c.cat_counts->>'음식·음료')::float8, 0),
                   coalesce((c.cat_counts->>'유통')::float8, 0)
                     + coalesce((c.cat_counts->>'패션·뷰티')::float8, 0)
            from commerce_obs c
            join places p on p.id = c.place_id
            where p.tier = 'A1' and c.ts < %s
            """,
            (datetime.combine(today, datetime.min.time()).replace(tzinfo=KST),),
        )
        frame = pd.DataFrame(cur.fetchall(), columns=["place_id", "ts", "pay_cnt", "food", "shop"])
    hourly = hourly_commerce(frame)
    cur_rows = []
    for place_id, part in hourly.groupby("place_id"):
        for row in profile_rows(part, kinds, today):
            cur_rows.append(
                (
                    place_id,
                    row["day_type"],
                    row["hour"],
                    row["a_all"],
                    row["a_food"],
                    row["a_shop"],
                    row["n_days"],
                )
            )
    with conn.cursor() as cur:
        cur.execute("delete from lively_profile")
        cur.executemany(
            """
            insert into lively_profile (place_id, day_type, hour, a_all, a_food, a_shop, n_days)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            cur_rows,
        )
    conn.commit()


def _write_forecasts(conn, started, today, model, passing, version: str, ready_ids: set) -> None:
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, tier from places
            where tier in ('A1', 'A2') and serve_state <> 'off' and serve_state <> 'experimental'
            """
        )
        places = cur.fetchall()
        cur.execute(
            """
            select place_id, max(ts) from live_obs group by place_id
            """
        )
        newest = dict(cur.fetchall())
        cur.execute("select place_id, t1, t2, t3 from level_thresholds")
        cuts = {row[0]: row[1:] for row in cur.fetchall()}
        cur.execute(
            """
            select place_id, day_type, hour, a_all, a_food, a_shop from lively_profile
            """
        )
        profiles = {(row[0], row[1], row[2]): row[3:] for row in cur.fetchall()}
        cur.execute("select date, kind from holidays")
        kinds = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            """
            select place_id, ts, (pop_min + pop_max) / 2.0, level
            from live_obs
            where ts >= %s and ts < %s
            """,
            (start - timedelta(days=35), start + timedelta(days=8)),
        )
        history = pd.DataFrame(cur.fetchall(), columns=["place_id", "ts", "value", "level"])
    hourly = hourly_frame(history, "floor") if not history.empty else pd.DataFrame()
    series = {}
    if not hourly.empty:
        for place_id, part in hourly.groupby("place_id"):
            indexed = part.set_index("hour")["value"]
            series[place_id] = indexed[~indexed.index.duplicated(keep="last")]
    forecast_rows = []
    log_rows = []
    for place_id, tier in places:
        place_series = series.get(place_id, pd.Series(dtype=float))
        fresh = newest.get(place_id)
        stale = fresh is None or fresh < started - timedelta(minutes=90)
        t1, t2, t3 = cuts.get(place_id, (float("inf"), float("inf"), float("inf")))
        threshold_ready = place_id in ready_ids
        for offset in range(8):
            day = today + timedelta(days=offset)
            dtype = day_type(day, kinds)
            for hour in range(24):
                target = datetime.combine(day, datetime.min.time()).replace(tzinfo=KST)
                target = target + timedelta(hours=hour)
                base = baseline(place_series, pd.Timestamp(target), offset)
                activity = activity_for(
                    tier, profiles.get((place_id, dtype, hour), (None, None, None))
                )
                pop = None
                level = None
                ready = False
                source = "profile"
                if base is not None:
                    if model is not None and place_id in model.place_index and offset in passing:
                        ratio = model.ratio(place_id, [target], offset)
                        pop = float(base) * math.exp(float(ratio[0]))
                        source = "model"
                    else:
                        pop = float(base)
                        source = "profile"
                    if threshold_ready and t1 <= t2 <= t3:
                        level = level_of(pop, t1, t2, t3)
                        ready = True
                forecast_rows.append(
                    (
                        place_id,
                        target,
                        started,
                        source,
                        pop,
                        level,
                        activity[0],
                        activity[1],
                        activity[2],
                        stale,
                        ready,
                    )
                )
                if offset in (1, 3, 7) and 9 <= hour <= 23 and pop is not None and base is not None:
                    log_rows.append((place_id, today, target, offset, pop, float(base), version))
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into forecast_hourly
              (place_id, target_ts, issued_ts, source, pop, level, a_all, a_food, a_shop, stale, ready)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (place_id, target_ts) do update set
              issued_ts = excluded.issued_ts,
              source = excluded.source,
              pop = excluded.pop,
              level = excluded.level,
              a_all = excluded.a_all,
              a_food = excluded.a_food,
              a_shop = excluded.a_shop,
              stale = excluded.stale,
              ready = excluded.ready
            """,
            forecast_rows,
        )
        cur.executemany(
            """
            insert into forecast_log
              (place_id, issued_date, target_ts, horizon_d, pred, baseline, model_version)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict do nothing
            """,
            log_rows,
        )
        apply_overlay(conn, started)
    conn.commit()


def _threshold_ready_flag(place_id, ready_ids: set) -> bool:
    return place_id in ready_ids
