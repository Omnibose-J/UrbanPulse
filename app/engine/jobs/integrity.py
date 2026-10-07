"""Read-only sweep of the stored rows. `python -m engine integrity [--full]`.

Every check is a count that must be 0. `ALWAYS` holds at any moment; `AFTER_FORECAST` holds
once the daily forecast has run (between midnight and that run the tables still hold
yesterday's eight days). `forecast` runs both sets when it finishes, `collect` runs `ALWAYS`.
"""

from __future__ import annotations

from engine import db, settings
from engine.log import log

JOB = "integrity"

_TODAY = "(now() at time zone 'Asia/Seoul')::date"
_CELLS = "recommendations r cross join lateral jsonb_array_elements(r.hours) c"

ALWAYS: dict[str, str] = {
    "served row without 15 hour cells": (
        "select count(*) from recommendations where state <> 'off' and jsonb_array_length(hours) <> 15"
    ),
    "off row carrying computed columns": (
        "select count(*) from recommendations where state = 'off' "
        "and (windows is not null or hours is not null or strip_mode is not null)"
    ),
    "window cell that is not rated 1": (
        f"select count(*) from {_CELLS} where r.state <> 'off' "
        "and (c->>'in_window')::boolean and (c->>'rating')::int = 0"
    ),
    "rating and reason disagree": (
        f"select count(*) from {_CELLS} where r.state <> 'off' "
        "and (((c->>'rating')::int = 0) = (c->>'reason' = 'fit'))"
    ),
    "activity text on a place that has none": (
        f"select count(*) from {_CELLS} join places p on p.id = r.place_id "
        "where p.tier <> 'A1' and r.state <> 'off' and c->>'act' is not null"
    ),
    "window hours differ from the in_window cells": """
        select count(*) from recommendations r where r.state <> 'off' and
          (select coalesce(jsonb_agg(h order by h), '[]'::jsonb) from (
             select (c->>'h')::int h from jsonb_array_elements(r.hours) c where (c->>'in_window')::boolean) a)
          is distinct from
          (select coalesce(jsonb_agg(distinct h order by h), '[]'::jsonb) from (
             select jsonb_array_elements_text(w->'hours')::int h
             from jsonb_array_elements(coalesce(r.windows, '[]'::jsonb)) w) b)
    """,
    "cell crowd differs from the forecast level of that hour": f"""
        select count(*) from {_CELLS}
        join forecast_hourly f on f.place_id = r.place_id
         and f.target_ts = ((r.date::text || ' ' || lpad(c->>'h', 2, '0') || ':00+09')::timestamptz)
        where r.state <> 'off' and r.date >= {_TODAY} and (c->>'crowd')::int <> f.level
    """,
    "window of today starting before the hour it was built": f"""
        select count(*) from recommendations r cross join lateral jsonb_array_elements(r.windows) w
        where r.date = {_TODAY} and r.state <> 'off'
          and (r.generated_at at time zone 'Asia/Seoul')::date = r.date
          and (w->'hours'->>0)::int < extract(hour from r.generated_at at time zone 'Asia/Seoul')
    """,
    "alternative date that is off or has no window": f"""
        select count(*) from recommendations r cross join lateral jsonb_array_elements(r.alt_dates) a
        join recommendations o on o.place_id = r.place_id and o.date = (a->>'date')::date
         and o.tolerance = r.tolerance and o.purpose = r.purpose
        where r.state <> 'off' and r.date >= {_TODAY} and (o.state = 'off' or o.no_window)
    """,
    "alternative place that is off or has no window": f"""
        select count(*) from recommendations r cross join lateral jsonb_array_elements(r.alt_places) a
        join recommendations o on o.place_id = a->>'place_id' and o.date = r.date
         and o.tolerance = r.tolerance and o.purpose = r.purpose
        where r.state <> 'off' and r.date >= {_TODAY} and (o.state = 'off' or o.no_window)
    """,
    "alternative date in the past": f"""
        select count(*) from recommendations r cross join lateral jsonb_array_elements(r.alt_dates) a
        where r.date >= {_TODAY} and (a->>'date')::date < {_TODAY}
    """,
    "ready forecast hour without a level": (
        "select count(*) from forecast_hourly where ready and level is null"
    ),
    "future hour marked live": (
        "select count(*) from forecast_hourly where source = 'live' and target_ts > now()"
    ),
    "city forecast hour more than 13 hours ahead": (
        "select count(*) from forecast_hourly "
        "where source = 'seoul' and target_ts > now() + interval '13 hours'"
    ),
    "thresholds out of order": "select count(*) from level_thresholds where not (t1 <= t2 and t2 <= t3)",
    "commerce row without the eight categories": (
        "select count(*) from commerce_obs where ts > now() - interval '2 days' "
        "and (select count(*) from jsonb_object_keys(cat_counts)) not in (8, 9)"
    ),
    "observation dated in the future": (
        "select count(*) from live_obs where ts > now() + interval '10 minutes'"
    ),
    "job stuck in running for over two hours": (
        "select count(*) from job_runs where status = 'running' and started_at < now() - interval '2 hours'"
    ),
}

AFTER_FORECAST: dict[str, str] = {
    "served A1/A2 place without 8 days of 24 forecast hours": """
        select count(*) from places p where p.serve_state = 'on' and p.tier <> 'B'
          and (select count(*) from forecast_hourly f where f.place_id = p.id) <> 192
    """,
    "served A1/A2 place without all its recommendation rows": """
        select count(*) from places p where p.serve_state = 'on' and p.tier <> 'B'
          and (select count(*) from recommendations r where r.place_id = p.id)
              <> 8 * 3 * (case when p.tier = 'A1' then 3 else 1 end)
    """,
    "recommendation row for a past date": f"select count(*) from recommendations where date < {_TODAY}",
    "forecast hour before today": (
        "select count(*) from forecast_hourly where target_ts < "
        "date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'"
    ),
    "measured activity on a row that is not one of today's A1 hours": f"""
        select count(*) from forecast_hourly f join places p on p.id = f.place_id
        where f.a_actual and (p.tier <> 'A1' or (f.target_ts at time zone 'Asia/Seoul')::date <> {_TODAY})
    """,
    "forecast or recommendation row of a place that is off": """
        select (select count(*) from forecast_hourly f join places p on p.id = f.place_id
                where p.serve_state = 'off')
             + (select count(*) from recommendations r join places p on p.id = r.place_id
                where p.serve_state = 'off')
    """,
}

_SERVED = "exists (select 1 from places where serve_state = 'on' and tier <> 'B')"
_MIDNIGHT = "date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'"

# Freshness, for the hourly job only: a paused scheduler or a stopped job fails no execution of its
# own, so the data would age silently. collect runs every 30 minutes; forecast at 05:10 KST.
FRESHNESS: dict[str, str] = {
    "no observation stored in the last two hours": f"""
        select count(*) from (select 1) one where {_SERVED}
          and not exists (select 1 from live_obs where ts >= now() - interval '2 hours')
    """,
    "served A1/A2 place without a forecast issued today (after 07:00)": f"""
        select count(*) from places p where p.serve_state = 'on' and p.tier <> 'B'
          and extract(hour from now() at time zone 'Asia/Seoul') >= 7
          and not exists (
            select 1 from forecast_hourly f where f.place_id = p.id and f.issued_ts >= {_MIDNIGHT}
          )
    """,
}


def sweep(conn, full: bool = False, fresh: bool = False) -> dict[str, int]:
    """Run the checks and return only the ones that are not 0."""
    checks = {**ALWAYS, **(AFTER_FORECAST if full else {}), **(FRESHNESS if fresh else {})}
    found: dict[str, int] = {}
    with conn.cursor() as cur:
        for name, sql in checks.items():
            cur.execute(sql)
            count = cur.fetchone()[0]
            if count:
                found[name] = int(count)
    return found


def run(full: bool = False) -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    with db.ledger(env["DATABASE_URL"], JOB) as (conn, ctx):
        found = sweep(conn, full, fresh=True)
        conn.rollback()
        ctx["detail"] = {
            "full": full,
            "checks": len(ALWAYS) + len(FRESHNESS) + (len(AFTER_FORECAST) if full else 0),
            "found": found,
        }
        ctx["status"] = "warn" if found else "ok"
    for name, count in found.items():
        print(f"{count:>7}  {name}")
    log(JOB, "done", full=full, found=len(found))
    return 1 if found else 0
