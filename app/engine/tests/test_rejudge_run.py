"""rejudge records string keys and leaves the flag file alone unless asked."""

from datetime import date, timedelta
from pathlib import Path

import psycopg

from engine.jobs import rejudge
from engine.tests.tempdb import schema

FLAGS = """version: 1
judged_at: "2026-10-02"
lively_min: {sight: 0.5, food: 0.5, shop: 0.6}
combos:
  - {group: a1, purpose: sight, tolerance: calm, state: off, strip: windows_only}
  - {group: a1, purpose: sight, tolerance: moderate, state: on, strip: windows_only}
"""


def test_rejudge_records_and_apply_changes_only_the_diff(tmp_path, monkeypatch):
    flags = Path(tmp_path / "flags.yaml")
    flags.write_text(FLAGS, encoding="utf-8")
    before = flags.read_bytes()
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                for index in range(12):
                    cur.execute(
                        "insert into places (id, tier, name, foreign_heavy, serve_state) "
                        "values (%s, 'A1', %s, false, 'on')",
                        (f"POI{index:03d}", f"P{index}"),
                    )
                start = date(2026, 1, 1)
                rows = []
                for day in range(30):
                    for index in range(12):
                        rows.append(
                            (
                                start + timedelta(days=day),
                                f"POI{index:03d}",
                                "sight",
                                "calm",
                                10,
                                10,
                                10,
                                10,
                                10,
                            )
                        )
                cur.executemany(
                    """
                    insert into reco_eval_daily (
                      date, place_id, purpose, tolerance, n_hours, n_lively,
                      n_crowd_ok, chance_hours, chance_lively
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
            conn.commit()
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        assert rejudge.run(apply=False, flags_path=flags) == 0
        assert flags.read_bytes() == before
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            detail = conn.execute("select detail from job_runs where job = 'rejudge'").fetchone()[0]
        assert detail["changes"]["a1/sight/calm"] == "on"
        assert rejudge.run(apply=True, flags_path=flags) == 0
        text = flags.read_text(encoding="utf-8")
        assert "purpose: sight, tolerance: calm, state: on" in text
        assert "purpose: sight, tolerance: moderate, state: on" in text


def _seed(conn, places: int, days: int) -> None:
    with conn.cursor() as cur:
        for index in range(places):
            cur.execute(
                "insert into places (id, tier, name, foreign_heavy, serve_state) values (%s, 'A1', "
                "%s, false, 'on')",
                (f"POI{index:03d}", f"P{index}"),
            )
        start = date(2026, 1, 1)
        cur.executemany(
            """
            insert into reco_eval_daily (
              date, place_id, purpose, tolerance, n_hours, n_lively, n_crowd_ok, chance_hours, chance_lively
            ) values (%s, %s, 'sight', 'calm', 10, 10, 10, 10, 10)
            """,
            [
                (start + timedelta(days=day), f"POI{index:03d}")
                for day in range(days)
                for index in range(places)
            ],
        )
    conn.commit()


def _run(monkeypatch, tmp_path, places: int, days: int, apply: bool):
    flags = Path(tmp_path / "flags.yaml")
    flags.write_text(FLAGS, encoding="utf-8")
    before = flags.read_bytes()
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            _seed(conn, places, days)
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        code = rejudge.run(apply=apply, flags_path=flags)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            detail = conn.execute("select detail from job_runs where job = 'rejudge'").fetchone()[0]
    return code, detail, flags.read_bytes() == before


def test_twenty_seven_days_are_not_enough_to_judge(monkeypatch, tmp_path):
    code, detail, unchanged = _run(monkeypatch, tmp_path, places=12, days=27, apply=True)
    assert code == 0
    assert "a1 sight calm insufficient" in detail["table"]
    assert detail["changes"] == {}
    assert unchanged


def test_nine_places_are_not_enough_to_judge(monkeypatch, tmp_path):
    code, detail, unchanged = _run(monkeypatch, tmp_path, places=9, days=30, apply=True)
    assert code == 0
    assert "a1 sight calm insufficient" in detail["table"]
    assert detail["changes"] == {}
    assert unchanged


def test_twenty_eight_days_and_ten_places_are_judged(monkeypatch, tmp_path):
    code, detail, unchanged = _run(monkeypatch, tmp_path, places=10, days=28, apply=False)
    assert code == 0
    assert "a1 sight calm PASS on" in detail["table"]
    assert detail["changes"] == {"a1/sight/calm": "on"}
    assert unchanged
