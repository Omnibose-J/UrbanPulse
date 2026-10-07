"""Daily forecast. `python -m engine forecast`.

Refreshes place state, thresholds and activity profiles, then writes today's 8-day
`forecast_hourly` rows and an append-only `forecast_log`.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
from psycopg.types.json import Jsonb

from engine import db, settings
from engine.calendar_feats import day_type
from engine.flags import load as load_flags
from engine.hourly import baseline, hourly_frame
from engine.jobs import integrity
from engine.levels import level_of, thresholds_for
from engine.lively import activity_update, hourly_commerce, p90_scales, profile_rows
from engine.log import log
from engine.parsers import KST
from engine.ratio_model import load
from engine.reco import build_row, fill_alternatives, log_candidates, purposes_for
from engine.similar import replace_similar

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


def activity_for(tier: str, stored: tuple) -> tuple:
    """A2 rows carry no activity profile."""
    if tier != "A1":
        return (None, None, None)
    return stored


def _today(now: datetime):
    return now.astimezone(KST).date()


def issued_midnight(today):
    """Start of the issued day. Later clock time must not move this."""
    return datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)


def drop_past_forecasts(conn, today) -> None:
    """Drop hours before the issued day, not before whatever day the clock shows now."""
    with conn.cursor() as cur:
        cur.execute("delete from forecast_hourly where target_ts < %s", (issued_midnight(today),))


def drop_unbuilt_forecasts(conn, started: datetime, today) -> None:
    """Hours this run did not write are not part of the forecast anymore."""
    with conn.cursor() as cur:
        cur.execute(
            """
            delete from forecast_hourly
            where target_ts >= %s and issued_ts is distinct from %s
            """,
            (issued_midnight(today), started),
        )


def lock_forecast_rows(cur, place_ids: list[str]) -> None:
    """Lock forecast rows in place_id, target_ts order so two jobs cannot deadlock."""
    ids = sorted(set(place_ids))
    if not ids:
        return
    cur.execute(
        """
        select place_id, target_ts
        from forecast_hourly
        where place_id = any(%s)
        order by place_id, target_ts
        for update
        """,
        (ids,),
    )


def apply_overlay(conn, now: datetime, place_ids: list[str]) -> None:
    """Hours with a live observation become `live`; later hours covered by city_fcst become `seoul`.

    One update statement per place, only for places just stored. Rows are locked in
    place_id, target_ts order first.
    """
    ids = sorted(set(place_ids))
    if not ids:
        return
    issued = issued_midnight(_today(now))
    hour_start = now.astimezone(KST).replace(minute=0, second=0, microsecond=0)
    horizon = issued + timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute("set time zone 'Asia/Seoul'")
        lock_forecast_rows(cur, ids)
        cur.execute(
            """
            select place_id, ts, (pop_min + pop_max) / 2.0, level
            from live_obs
            where place_id = any(%s) and ts >= %s and ts < %s
            order by place_id, ts
            """,
            (ids, issued, horizon),
        )
        live_rows = pd.DataFrame(cur.fetchall(), columns=["place_id", "ts", "value", "level"])
        cur.execute(
            """
            select place_id, target_ts, (pop_min + pop_max) / 2.0, level
            from city_fcst
            where place_id = any(%s) and target_ts >= %s and target_ts < %s
            order by place_id, target_ts
            """,
            (ids, hour_start, horizon),
        )
        city_rows = cur.fetchall()
        cur.execute(
            """
            select place_id, max(ts)
            from live_obs
            where place_id = any(%s)
            group by place_id
            """,
            (ids,),
        )
        newest = dict(cur.fetchall())
        if not live_rows.empty:
            hourly = hourly_frame(live_rows, "floor")
            for place_id, part in hourly.groupby("place_id", sort=True):
                part = part.sort_values("hour")
                cur.execute(
                    """
                    update forecast_hourly as forecast
                    set source = 'live', pop = v.pop, level = v.level, ready = true
                    from unnest(%s::timestamptz[], %s::float8[], %s::int[]) as v(target_ts, pop, level)
                    where forecast.place_id = %s and forecast.target_ts = v.target_ts
                    """,
                    (
                        [stamp.to_pydatetime() for stamp in part["hour"]],
                        [float(value) for value in part["value"]],
                        [None if pd.isna(level) else int(level) for level in part["level"]],
                        place_id,
                    ),
                )
        by_place: dict[str, list[tuple]] = {}
        for place_id, target, pop, level in city_rows:
            by_place.setdefault(place_id, []).append((target, float(pop), int(level)))
        for place_id in sorted(by_place):
            rows = sorted(by_place[place_id], key=lambda item: item[0])
            cur.execute(
                """
                update forecast_hourly as forecast
                set source = 'seoul', pop = v.pop, level = v.level, ready = true
                from unnest(%s::timestamptz[], %s::float8[], %s::int[]) as v(target_ts, pop, level)
                where forecast.place_id = %s
                  and forecast.target_ts = v.target_ts
                  and forecast.source <> 'live'
                """,
                ([row[0] for row in rows], [row[1] for row in rows], [row[2] for row in rows], place_id),
            )
    _measure_activity(conn, now, ids)
    cutoff = now.astimezone(KST) - timedelta(minutes=90)
    with conn.cursor() as cur:
        for place_id in ids:
            fresh = newest.get(place_id)
            stale = fresh is None or fresh < cutoff
            cur.execute(
                "update forecast_hourly set stale = %s where place_id = %s",
                (stale, place_id),
            )


def require_model_files(directory, version: str) -> None:
    """Exit 1 when an active registry row has no artifact or a different version."""
    meta_path = directory / "meta.json"
    artifact = directory / "model.joblib"
    if not meta_path.is_file() or not artifact.is_file():
        print(f"missing model: {directory}", file=sys.stderr)
        raise SystemExit(1)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("created_at") != version:
        print(f"model version mismatch: {meta_path}", file=sys.stderr)
        raise SystemExit(1)


def _active_model(conn):
    root = settings.MODELS_DIR / "ratio_v1"
    with conn.cursor() as cur:
        cur.execute(
            """
            select version, horizons from model_registry
            where name = 'ratio_v1' and active
            order by created_at desc
            limit 1
            """
        )
        row = cur.fetchone()
    if row is None:
        if not (root / "meta.json").is_file():
            return None, []
        return load(root), []
    require_model_files(root, row[0])
    return load(root), list(row[1] or [])


def run() -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    started = datetime.now(KST)
    today = _today(started)
    log(JOB, "start", issued=today.isoformat())
    try:
        with db.ledger(env["DATABASE_URL"], JOB) as (conn, ctx):
            ctx["detail"] = _build(conn, started, today)
            detail = ctx["detail"]
            found = integrity.sweep(conn, full=True)
            conn.rollback()
            if found:
                detail["integrity"] = found
                ctx["status"] = "warn"
    except BaseException as exc:
        log(JOB, "fail", reason=type(exc).__name__)
        raise
    log(JOB, "done", places=detail.get("places"), transitions=len(detail.get("transitions", {})))
    return 0


def _lap(mark: list[float], timing: dict, name: str) -> None:
    now = time.perf_counter()
    timing[name] = round(now - mark[0], 1)
    mark[0] = now


def _build(conn, started: datetime, today) -> dict:
    timing: dict[str, float] = {}
    mark = [time.perf_counter()]
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
    _lap(mark, timing, "refresh")
    with conn.cursor() as cur:
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
    _lap(mark, timing, "thresholds")
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
    timing["refresh"] = round(timing["refresh"] + (time.perf_counter() - mark[0]), 1)
    mark[0] = time.perf_counter()
    _write_profiles(conn, today)
    _lap(mark, timing, "profile")
    forecast_logs = _write_forecasts(conn, started, today, model, set(passing), version, ready_ids)
    timing["forecast_hourly"] = round(time.perf_counter() - mark[0], 1)
    mark[0] = time.perf_counter()
    _write_tier_b_forecasts(conn, started, today)
    drop_unbuilt_forecasts(conn, started, today)
    drop_past_forecasts(conn, today)
    _lap(mark, timing, "tier B")
    similar = replace_similar(conn, today)
    reco = refresh_recommendations(conn, started, today)
    conn.commit()
    log_started = time.perf_counter()
    reco["logged"] = _insert_logs(conn, forecast_logs, reco.pop("log_rows"))
    conn.commit()
    timing["log"] = round(time.perf_counter() - log_started, 1)
    _lap(mark, timing, "recommendations")
    return {
        "transitions": transitions,
        "places": len(places),
        "passing_horizons": list(passing),
        "similar": similar,
        "reco": reco,
        "levels_rule": "split",
        "timing": timing,
    }

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
    norm_rows = []
    for place_id, part in hourly.groupby("place_id"):
        profiles = list(profile_rows(part, kinds, today))
        if not profiles:
            continue
        scales = p90_scales(part, kinds, today)
        norm_rows.append((place_id, scales["all"], scales["food"], scales["shop"]))
        for row in profiles:
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
        cur.execute("delete from lively_norm")
        cur.executemany(
            """
            insert into lively_norm (place_id, p90_all, p90_food, p90_shop)
            values (%s, %s, %s, %s)
            """,
            norm_rows,
        )


def _write_forecasts(conn, started, today, model, passing, version: str, ready_ids: set) -> list:
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, tier from places
            where tier in ('A1', 'A2') and serve_state <> 'off' and serve_state <> 'experimental'
            order by id
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
        holiday_rows = cur.fetchall()
        kinds = {row[0]: row[1] for row in holiday_rows}
        holiday_dates = [row[0] for row in holiday_rows]
        seol_starts = [row[0] for row in holiday_rows if row[1] == "seol"]
        chuseok_starts = [row[0] for row in holiday_rows if row[1] == "chuseok"]
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
            midnight = datetime.combine(day, datetime.min.time()).replace(tzinfo=KST)
            targets = [midnight + timedelta(hours=hour) for hour in range(24)]
            use_model = model is not None and place_id in model.place_index and offset in passing
            ratios = (
                model.ratio(place_id, targets, offset, holiday_dates, seol_starts, chuseok_starts)
                if use_model
                else None
            )
            for hour, target in enumerate(targets):
                base = baseline(place_series, pd.Timestamp(target), offset)
                activity = activity_for(
                    tier, profiles.get((place_id, dtype, hour), (None, None, None))
                )
                pop = None
                level = None
                ready = False
                source = "profile"
                if base is not None:
                    if ratios is not None:
                        pop = float(base) * math.exp(float(ratios[hour]))
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
    forecast_rows.sort(key=lambda row: (row[0], row[1]))
    with conn.pipeline(), conn.cursor() as cur:
        lock_forecast_rows(cur, [row[0] for row in forecast_rows])
        cur.executemany(
            """
            insert into forecast_hourly (
              place_id, target_ts, issued_ts, source, pop, level,
              a_all, a_food, a_shop, stale, ready, a_actual
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
            on conflict (place_id, target_ts) do update set
              issued_ts = excluded.issued_ts,
              source = excluded.source,
              pop = excluded.pop,
              level = excluded.level,
              a_all = excluded.a_all,
              a_food = excluded.a_food,
              a_shop = excluded.a_shop,
              stale = excluded.stale,
              ready = excluded.ready,
              a_actual = false
            """,
            forecast_rows,
        )
    apply_overlay(conn, started, [place_id for place_id, _tier in places])
    return log_rows


_P90_KEY = {"sight": 0, "food": 1, "shop": 2}


def _measure_activity(conn, now: datetime, place_ids: list[str]) -> None:
    """A1 hours with commerce today take measured activity and a_actual."""
    today = _today(now)
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)
    end = start + timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.place_id,
                   date_trunc('hour', c.ts at time zone 'Asia/Seoul'),
                   avg(c.pay_cnt)::float8,
                   avg(coalesce((c.cat_counts->>'음식·음료')::float8, 0)),
                   avg(coalesce((c.cat_counts->>'유통')::float8, 0)
                     + coalesce((c.cat_counts->>'패션·뷰티')::float8, 0))
            from commerce_obs c
            join places p on p.id = c.place_id and p.tier = 'A1'
            where c.ts >= %s and c.ts < %s and c.place_id = any(%s)
            group by 1, 2
            order by 1, 2
            """,
            (start, end, place_ids),
        )
        measured = cur.fetchall()
        cur.execute("select place_id, p90_all, p90_food, p90_shop from lively_norm")
        norms = {row[0]: row[1:] for row in cur.fetchall()}
    updates = []
    for place_id, hour, pay, food, shop in measured:
        scales = norms.get(place_id, (None, None, None))
        stamp = hour.replace(tzinfo=KST) if hour.tzinfo is None else hour.astimezone(KST)
        values = []
        for value, scale in ((pay, scales[0]), (food, scales[1]), (shop, scales[2])):
            updated = activity_update("A1", True, float(value or 0), None if scale is None else float(scale))
            values.append(None if updated is None else updated[0])
        updates.append((values[0], values[1], values[2], place_id, stamp))
    updates.sort(key=lambda row: (row[3], row[4]))
    if not updates:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            update forecast_hourly
            set a_all = %s, a_food = %s, a_shop = %s, a_actual = true
            where place_id = %s and target_ts = %s
            """,
            updates,
        )


def level_from_rel(rel: float) -> int:
    if rel < 0.5:
        return 0
    if rel < 0.9:
        return 1
    return 2


def _write_tier_b_forecasts(conn, started, today) -> None:
    """Profile-only hours for tier B. No forecast_log rows."""
    with conn.cursor() as cur:
        cur.execute("select place_id, day_type, hour, rel from tier_b_profile")
        profiles = {(row[0], row[1], row[2]): float(row[3]) for row in cur.fetchall()}
    rows = []
    for place_id in {key[0] for key in profiles}:
        for offset in range(8):
            day = today + timedelta(days=offset)
            if day.weekday() == 6:
                dtype = "sun"
            elif day.weekday() == 5:
                dtype = "sat"
            else:
                dtype = "weekday"
            for hour in range(24):
                rel = profiles.get((place_id, dtype, hour))
                if rel is None:
                    continue
                target = datetime.combine(day, datetime.min.time()).replace(tzinfo=KST)
                target = target + timedelta(hours=hour)
                rows.append(
                    (
                        place_id,
                        target,
                        started,
                        "profile",
                        None,
                        rel,
                        level_from_rel(rel),
                        None,
                        None,
                        None,
                        False,
                        True,
                    )
                )
    rows.sort(key=lambda row: (row[0], row[1]))
    with conn.cursor() as cur:
        lock_forecast_rows(cur, [row[0] for row in rows])
        cur.executemany(
            """
            insert into forecast_hourly (
              place_id, target_ts, issued_ts, source, pop, rel, level,
              a_all, a_food, a_shop, stale, ready, a_actual
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)
            on conflict (place_id, target_ts) do update set
              issued_ts = excluded.issued_ts,
              source = excluded.source,
              pop = excluded.pop,
              rel = excluded.rel,
              level = excluded.level,
              a_all = excluded.a_all,
              a_food = excluded.a_food,
              a_shop = excluded.a_shop,
              stale = excluded.stale,
              ready = excluded.ready,
              a_actual = false
            """,
            rows,
        )


def refresh_recommendations(conn, started: datetime, today, place_ids=None, only_today: bool = False) -> dict:
    """Upsert recommendation rows. The full forecast also logs today+3 and drops past dates."""
    flags = load_flags()
    dates = [today] if only_today else [today + timedelta(days=offset) for offset in range(8)]
    start = datetime.combine(dates[0], datetime.min.time()).replace(tzinfo=KST)
    end = datetime.combine(dates[-1] + timedelta(days=1), datetime.min.time()).replace(tzinfo=KST)
    with conn.cursor() as cur:
        cur.execute("set time zone 'Asia/Seoul'")
        cur.execute(
            """
            select id, tier, foreign_heavy, serve_state, open_hours, lat, lon
            from places
            where (
              tier in ('A1', 'A2') and serve_state <> 'off' and serve_state <> 'experimental'
            ) or (
              tier = 'B' and exists (select 1 from tier_b_profile t where t.place_id = places.id)
            )
            """
        )
        places = [
            {
                "id": row[0],
                "tier": row[1],
                "foreign_heavy": row[2],
                "serve_state": row[3],
                "open_hours": row[4],
                "lat": row[5],
                "lon": row[6],
            }
            for row in cur.fetchall()
        ]
        if place_ids is not None:
            wanted = set(place_ids)
            places = [
                place
                for place in places
                if place["id"] in wanted or (only_today and place["tier"] == "B")
            ]
        cur.execute("select date, kind from holidays")
        kinds = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            """
            select place_id, target_ts, level, a_all, a_food, a_shop, ready
            from forecast_hourly
            where target_ts >= %s and target_ts < %s
            """,
            (start, end),
        )
        hourly_rows = cur.fetchall()
        cur.execute("select place_id, other_id from similar_places order by place_id, rank")
        neighbours: dict[str, list[str]] = {}
        for place_id, other_id in cur.fetchall():
            neighbours.setdefault(place_id, []).append(other_id)
        cur.execute("select id, lat, lon from places")
        coords = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        cur.execute("select place_id, p90_all, p90_food, p90_shop from lively_norm")
        norms = {row[0]: row[1:] for row in cur.fetchall()}
        stored = []
        if only_today and places:
            # The pool for alternatives: the refreshed places' other dates (their alt dates point at
            # today), and today's rows of every place this refresh did not re-score, whose alt places may
            # point at a window the refresh just removed. Both get their alternatives rewritten below;
            # nothing else of theirs changes.
            refreshed = [place["id"] for place in places]
            cur.execute(
                """
                select r.place_id, r.date, r.tolerance, r.purpose, r.state, r.windows, p.tier
                from recommendations r
                join places p on p.id = r.place_id
                where (r.place_id = any(%s) and r.date > %s and r.date <= %s)
                   or (r.date = %s and not r.place_id = any(%s))
                """,
                (refreshed, today, today + timedelta(days=7), today, refreshed),
            )
            stored = [
                {
                    "place_id": row[0],
                    "date": row[1],
                    "tolerance": row[2],
                    "purpose": row[3],
                    "state": row[4],
                    "windows": row[5],
                    "tier": row[6],
                    # Another place's today row: the pool holds none of its other dates, so only its
                    # alt places are rewritten (its alt dates would come out empty).
                    "places_only": row[1] == today and row[0] not in refreshed,
                }
                for row in cur.fetchall()
            ]
    hourly = {}
    for place_id, target, level, a_all, a_food, a_shop, ready in hourly_rows:
        local = target.astimezone(KST)
        hourly.setdefault((place_id, local.date()), {})[local.hour] = {
            "level": level,
            "a_all": a_all,
            "a_food": a_food,
            "a_shop": a_shop,
            "ready": ready,
        }
    built = []
    for place in places:
        for day in dates:
            kind = day_type(day, kinds)
            slots = hourly.get((place["id"], day), {})
            for purpose in purposes_for(place["tier"]):
                for tolerance in ("calm", "moderate", "busy_ok"):
                    now_hour = started.astimezone(KST).hour if day == today else None
                    row = build_row(place, day, tolerance, purpose, slots, flags, kind, now_hour)
                    scales = norms.get(place["id"])
                    if place["tier"] == "A1" and scales is not None and purpose in _P90_KEY:
                        row["p90"] = scales[_P90_KEY[purpose]]
                    built.append(row)
    pool = built + stored
    fill_alternatives(pool, pool, neighbours, coords)
    payload = [_recommendation_tuple(row, started) for row in built]
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into recommendations (
              place_id, date, tolerance, purpose, state, off_reason, windows, no_window, hours,
              strip_mode, alt_dates, alt_places, generated_at
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (place_id, date, tolerance, purpose) do update set
              state = excluded.state,
              off_reason = excluded.off_reason,
              windows = excluded.windows,
              no_window = excluded.no_window,
              hours = excluded.hours,
              strip_mode = excluded.strip_mode,
              alt_dates = excluded.alt_dates,
              alt_places = excluded.alt_places,
              generated_at = excluded.generated_at
            """,
            payload,
        )
        dated = [row for row in stored if row["state"] != "off" and not row["places_only"]]
        neighbours_only = [row for row in stored if row["state"] != "off" and row["places_only"]]
        if neighbours_only:
            cur.executemany(
                """
                update recommendations
                set alt_places = %s
                where place_id = %s and date = %s and tolerance = %s and purpose = %s
                """,
                [
                    (Jsonb(row["alt_places"]), row["place_id"], row["date"], row["tolerance"], row["purpose"])
                    for row in neighbours_only
                ],
            )
        if dated:
            cur.executemany(
                """
                update recommendations
                set alt_dates = %s, alt_places = %s
                where place_id = %s and date = %s and tolerance = %s and purpose = %s
                """,
                [
                    (
                        Jsonb(row["alt_dates"]),
                        Jsonb(row["alt_places"]),
                        row["place_id"],
                        row["date"],
                        row["tolerance"],
                        row["purpose"],
                    )
                    for row in dated
                ],
            )
        log_rows = []
        if not only_today:
            log_rows = [_log_tuple(row, today) for row in log_candidates(built, today)]
            cur.execute("delete from recommendations where date < %s", (today,))
            cur.execute(
                """
                delete from recommendations
                where date >= %s and generated_at is distinct from %s
                """,
                (today, started),
            )
    off_by: dict[str, int] = {}
    on = reference = no_window = 0
    for row in built:
        if row["state"] == "on":
            on += 1
        elif row["state"] == "reference":
            reference += 1
        else:
            off_by[row["off_reason"]] = off_by.get(row["off_reason"], 0) + 1
        if row["no_window"]:
            no_window += 1
    return {
        "rows": len(built),
        "on": on,
        "reference": reference,
        "off_by_reason": off_by,
        "no_window": no_window,
        "logged": 0,
        "log_rows": log_rows,
    }


def _insert_logs(conn, forecast_logs: list, recommendation_logs: list) -> int:
    """Append-only logs, after the web-visible tables have committed."""
    with conn.cursor() as cur:
        if forecast_logs:
            cur.executemany(
                """
                insert into forecast_log
                  (place_id, issued_date, target_ts, horizon_d, pred, baseline, model_version)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict do nothing
                """,
                forecast_logs,
            )
        cur.execute("select count(*) from recommendation_log")
        before = cur.fetchone()[0]
        if recommendation_logs:
            cur.executemany(
                """
                insert into recommendation_log (
                  place_id, issued_date, date, tolerance, purpose, state, windows, hours, p90, lively_min
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict do nothing
                """,
                recommendation_logs,
            )
        cur.execute("select count(*) from recommendation_log")
        return cur.fetchone()[0] - before


def _recommendation_tuple(row: dict, started: datetime):
    return (
        row["place_id"],
        row["date"],
        row["tolerance"],
        row["purpose"],
        row["state"],
        row["off_reason"],
        None if row["windows"] is None else Jsonb(row["windows"]),
        row["no_window"],
        None if row["hours"] is None else Jsonb(row["hours"]),
        row["strip_mode"],
        None if row["alt_dates"] is None else Jsonb(row["alt_dates"]),
        None if row["alt_places"] is None else Jsonb(row["alt_places"]),
        started,
    )


def _log_tuple(row: dict, issued):
    return (
        row["place_id"],
        issued,
        row["date"],
        row["tolerance"],
        row["purpose"],
        row["state"],
        Jsonb(row["windows"] or []),
        Jsonb(row["hours"]),
        row["p90"],
        row["lively_min"],
    )
