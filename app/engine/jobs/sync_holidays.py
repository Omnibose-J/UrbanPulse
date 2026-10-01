"""Fill `holidays` for 2023-01 .. 2027-12 from the KASI getRestDeInfo API.

The key travels only in the request URL. httpx errors are re-raised as HolidayError with the
year-month and the exception type, never the URL (same rule as healthcheck).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml

from engine import db, settings
from engine.log import log

JOB = "sync_holidays"
NEEDS = ("DATABASE_URL", "KASI_API_KEY")
KASI_URL = (
    "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
    "?solYear={year}&solMonth={month:02d}&numOfRows=100&pageNo=1&_type=json&ServiceKey={key}"
)
TIMEOUT = 20.0
PAUSE_S = 0.2
FIRST_YEAR = 2023
LAST_YEAR = 2027

_UPSERT = """
insert into holidays (date, name, name_en, kind)
values (%(date)s, %(name)s, %(name_en)s, %(kind)s)
on conflict (date) do update set
  name = excluded.name,
  name_en = excluded.name_en,
  kind = excluded.kind
where holidays.name is distinct from excluded.name
   or holidays.name_en is distinct from excluded.name_en
   or holidays.kind is distinct from excluded.kind
"""


class HolidayError(RuntimeError):
    """Raised with a year-month and a status. Never carries a URL or a key."""


def kind_of(date_name: str) -> str:
    """substitute if the name contains 대체, else seol / chuseok, else holiday."""
    if "대체" in date_name:
        return "substitute"
    if "설날" in date_name:
        return "seol"
    if "추석" in date_name:
        return "chuseok"
    return "holiday"


def english_name(date_name: str, table: dict[str, str]) -> str:
    """Exact name, otherwise the longest listed name that is a prefix or a substring."""
    if date_name in table:
        return table[date_name]
    matches = [key for key in table if date_name.startswith(key)]
    if not matches:
        matches = [key for key in table if key in date_name]
    if not matches:
        raise KeyError(date_name)
    return table[max(matches, key=len)]


def load_english_names(path: Path | None = None) -> dict[str, str]:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "holiday_names_en.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise HolidayError("holiday_names_en.yaml is empty")
    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value:
            raise HolidayError("holiday_names_en.yaml must map names to English strings")
        out[key] = value
    return out


def _items(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    try:
        header = payload["response"]["header"]
        body = payload["response"]["body"]
    except (KeyError, TypeError) as exc:
        raise HolidayError(f"kasi: unexpected payload ({type(exc).__name__})") from None
    code = str(header.get("resultCode", ""))
    raw_items = body.get("items") if isinstance(body, dict) else None
    if raw_items in (None, "", {}):
        return code, []
    if not isinstance(raw_items, dict):
        raise HolidayError(f"kasi: items {type(raw_items).__name__}")
    item = raw_items.get("item", [])
    if isinstance(item, dict):
        return code, [item]
    if isinstance(item, list):
        return code, [row for row in item if isinstance(row, dict)]
    raise HolidayError("kasi: item is neither an object nor a list")


def parse_month(payload: dict[str, Any], year: int, month: int) -> list[dict[str, Any]]:
    """Holiday rows for one month. resultCode 03 (no data) is an empty month."""
    code, items = _items(payload)
    label = f"{year}-{month:02d}"
    if code == "03" or (code == "00" and not items):
        return []
    if code != "00":
        raise HolidayError(f"kasi {label}: resultCode {code}")
    total = payload["response"]["body"].get("totalCount")
    if total is not None and int(total) > len(items):
        raise HolidayError(f"kasi {label}: totalCount {total} exceeds returned {len(items)}")
    rows: list[dict[str, Any]] = []
    for item in items:
        loc = str(item.get("locdate", ""))
        name = str(item.get("dateName", "")).strip()
        if len(loc) != 8 or not loc.isdigit() or not name:
            raise HolidayError(f"kasi {label}: bad item")
        day = date(int(loc[:4]), int(loc[4:6]), int(loc[6:8]))
        if day.year != year or day.month != month:
            raise HolidayError(f"kasi {label}: locdate {loc} is outside the month")
        rows.append(
            {
                "date": day,
                "name": name,
                "kind": kind_of(name),
                "is_holiday": str(item.get("isHoliday", "")).strip(),
            }
        )
    return rows


def _fetch_month(client: httpx.Client, key: str, year: int, month: int) -> list[dict[str, Any]]:
    url = KASI_URL.format(key=key, year=year, month=month)
    label = f"{year}-{month:02d}"
    try:
        response = client.get(url, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise HolidayError(f"kasi {label}: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise HolidayError(f"kasi {label}: HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise HolidayError(f"kasi {label}: invalid JSON") from None
    return parse_month(payload, year, month)


def day_off_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep API items the calendar marks as a day off (`isHoliday` = Y)."""
    return [row for row in rows if row.get("is_holiday") == "Y"]


def _with_english(rows: list[dict[str, Any]], table: dict[str, str]) -> list[dict[str, Any]]:
    """One row per date. Two API items on the same date become one row.

    The holidays primary key is the date. When the names differ, keep both in
    calendar order of the Korean names, joined with ' · ', and join the English
    the same way. kind stays holiday when both are holiday; a more specific kind
    (substitute, seol, chuseok) wins over holiday if they ever differ.
    """
    grouped: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["date"], []).append(row)
    unknown: set[str] = set()
    merged: dict[date, dict[str, Any]] = {}
    rank = {"holiday": 0, "seol": 1, "chuseok": 1, "substitute": 2}
    for day, items in grouped.items():
        names = sorted({item["name"] for item in items})
        kinds = {item["kind"] for item in items}
        try:
            english = [english_name(name, table) for name in names]
        except KeyError as exc:
            unknown.add(str(exc.args[0]))
            continue
        kind = max(kinds, key=lambda item: rank[item])
        merged[day] = {
            "date": day,
            "name": " · ".join(names),
            "name_en": " · ".join(english),
            "kind": kind,
        }
    if unknown:
        raise HolidayError("unknown holiday name: " + ", ".join(sorted(unknown)))
    return [merged[key] for key in sorted(merged)]


def run(client: httpx.Client | None = None, pause_s: float = PAUSE_S) -> int:
    settings.load_env()
    env = settings.require(NEEDS)
    table = load_english_names()
    own_client = client is None
    client = client or httpx.Client()
    collected: list[dict[str, Any]] = []
    log(JOB, "start", months=(LAST_YEAR - FIRST_YEAR + 1) * 12)
    try:
        index = 0
        for year in range(FIRST_YEAR, LAST_YEAR + 1):
            for month in range(1, 13):
                if index:
                    time.sleep(pause_s)
                index += 1
                collected.extend(_fetch_month(client, env["KASI_API_KEY"], year, month))
        watched = {
            row["date"].isoformat(): {"name": row["name"], "isHoliday": row["is_holiday"]}
            for row in collected
            if row["date"] in {date(2026, 5, 1), date(2026, 7, 17)}
        }
        rows = _with_english(day_off_rows(collected), table)
        if not rows:
            raise HolidayError("kasi returned no days off")
        with db.connect(env["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute("set time zone 'Asia/Seoul'")
                kept_dates = [row["date"] for row in rows]
                cur.execute(
                    """
                    delete from holidays
                    where date between '2023-01-01' and '2027-12-31'
                      and not (date = any(%s))
                    """,
                    (kept_dates,),
                )
                deleted = cur.rowcount
                cur.executemany(_UPSERT, rows)
                written = cur.rowcount
            conn.commit()
    except HolidayError as exc:
        log(JOB, "fail", reason=str(exc))
        return 1
    finally:
        if own_client:
            client.close()
    names = sorted({row["name"] for row in rows})
    shared = [f"{row['date'].isoformat()} {row['name']}" for row in rows if " · " in row["name"]]
    log(
        JOB,
        "done",
        rows=len(rows),
        written=written,
        deleted=deleted,
        watched=watched,
        names=names,
        shared_dates=shared,
    )
    return 0
