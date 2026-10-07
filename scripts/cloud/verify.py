"""Check a running site and the data behind it. One line per check; exit 1 when any line is not OK.

    python scripts/cloud/verify.py https://<deployment> --env-file .env.cloud
    python scripts/cloud/verify.py http://localhost:3100 --env-file .env

The env file supplies `DATABASE_URL`, `ADMIN_TOKEN`, `RAW_DIR` and the values that must not occur in anything
the site serves. No value is printed. A `gs://` RAW_DIR needs application-default credentials on this machine.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

from engine import db, raw_gcs, raw_store
from engine.parsers import KST

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_NAMES = (
    "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL", "ADMIN_TOKEN", "SEOUL_API_KEY", "KASI_API_KEY",
    "VAPID_PRIVATE_KEY", "CRON_SECRET",
)
SCHEDULED = {"collect": 45, "forecast": 26 * 60, "evaluate": 26 * 60}  # minutes a newest run may be old
PLACE = "POI001"


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def line(self, ok: bool, name: str, note: str = "") -> None:
        self.failed += 0 if ok else 1
        print(f"{'OK  ' if ok else 'FAIL'} {name}{' - ' + note if note else ''}")


def api_checks(today: str) -> list[tuple[str, set[str]]]:
    cond = "tolerance=moderate&purpose=sight"
    return [
        ("/api/health", {"db", "places"}),
        (f"/api/home?{cond}", {"as_of", "busy_top", "open_quiet", "stale", "tomorrow_morning"}),
        ("/api/places?q=%EA%B0%95%EB%82%A8", {"places"}),
        (f"/api/places/{PLACE}/week?{cond}", {"combos", "days", "now", "place"}),
        (f"/api/places/{PLACE}/day?date={today}", {"hours"}),
        (
            f"/api/places/{PLACE}/recommend?date={today}&{cond}",
            {"alt_dates", "alt_places", "combos", "holiday", "place", "recommendation"},
        ),
        (f"/api/map?date={today}&{cond}", {"holidays", "places"}),
        ("/api/flags", {"rows"}),
    ]


def site(report: Report, client: httpx.Client, env: dict[str, str], today: str) -> list[str]:
    """Run the HTTP checks; return every body fetched, for the secret search."""
    bodies: list[str] = []

    def get(path: str, **kwargs) -> httpx.Response | None:
        try:
            response = client.get(path, **kwargs)
        except httpx.HTTPError as exc:
            report.line(False, path.split("?")[0], type(exc).__name__)
            return None
        bodies.append(response.text)
        return response

    for path, keys in api_checks(today):
        response = get(path)
        if response is None:
            continue
        name = path.split("?")[0]
        if response.status_code != 200:
            report.line(False, name, f"HTTP {response.status_code}")
            continue
        report.line(set(response.json().keys()) == keys, name, f"keys {sorted(response.json().keys())}")

    # Weekend reminder: the worker file is served, the cron route refuses a call without the secret, and a
    # malformed subscription is refused with its field named.
    response = get("/sw.js")
    if response is not None:
        served = response.status_code == 200 and "push" in response.text
        report.line(served, "/sw.js", f"HTTP {response.status_code}")
    response = get("/api/push/weekend")
    if response is not None:
        refused = response.status_code == 401
        report.line(refused, "/api/push/weekend without secret", f"HTTP {response.status_code}")
    try:
        bad = client.post("/api/push/subscribe", json={"subscription": {"endpoint": "http://x"}})
        bodies.append(bad.text)
        report.line(bad.status_code == 400, "/api/push/subscribe malformed", f"HTTP {bad.status_code}")
    except httpx.HTTPError as exc:
        report.line(False, "/api/push/subscribe malformed", type(exc).__name__)

    launch_files = (
        ("/robots.txt", "Sitemap:"),
        ("/sitemap.xml", "<loc>"),
        ("/manifest.webmanifest", '"icons"'),
        ("/og.png", None),
        ("/icon-512.png", None),
    )
    for path, must_have in launch_files:
        response = get(path)
        if response is not None:
            ok = response.status_code == 200 and (must_have is None or must_have in response.text)
            report.line(ok, path, f"HTTP {response.status_code}")

    for path in ("/ko", "/en", "/ko/map", f"/ko/p/{PLACE}", "/ko/compare?a=POI001&b=POI002"):
        response = get(path)
        if response is not None:
            # Launched 2026-10-07: pages carry no noindex and do carry the CSP.
            noindex = "noindex" in response.headers.get("x-robots-tag", "")
            csp = "frame-ancestors 'none'" in response.headers.get("content-security-policy", "")
            report.line(
                response.status_code == 200 and not noindex and csp,
                path,
                f"HTTP {response.status_code} noindex={noindex} csp={csp}",
            )

    response = get("/vendor/maplibre/maplibre-gl-worker.mjs")
    if response is not None:
        kind = response.headers.get("content-type", "")
        ok = response.status_code == 200 and "javascript" in kind and len(response.content) > 10_000
        report.line(ok, "map worker file", f"HTTP {response.status_code} {kind.split(';')[0]}")

    response = get("/admin/eval")
    if response is not None:
        report.line(
            response.status_code == 404, "/admin/eval without a session", f"HTTP {response.status_code}"
        )
    # The token is never sent in an address here, not even to prove it is refused: that would put it in the
    # deployment's access log. e2e/admin.spec.ts proves that case against the local server.
    try:
        login = client.post("/admin/session", data={"token": env["ADMIN_TOKEN"]})
    except httpx.HTTPError as exc:
        report.line(False, "/admin/session", type(exc).__name__)
        return bodies
    cookie = login.headers.get("set-cookie", "")
    flags = cookie.lower()
    report.line(
        login.status_code == 303 and "httponly" in flags and "samesite=strict" in flags,
        "/admin/session sets an httpOnly, SameSite=Strict cookie",
        f"HTTP {login.status_code}",
    )
    # Sent by hand: the cookie is Secure in production and this client would not return it over plain http.
    response = get("/admin/eval", headers={"Cookie": cookie.split(";")[0]})
    if response is not None:
        report.line(response.status_code == 200 and "Jobs" in response.text, "/admin/eval with the session")
    return bodies


def data(report: Report, env: dict[str, str], today: datetime) -> None:
    conn = db.connect(env["DATABASE_URL"])
    try:
        for job, limit in SCHEDULED.items():
            row = conn.execute(
                "select status, extract(epoch from now() - started_at) / 60 from job_runs "
                "where job = %s order by id desc limit 1",
                (job,),
            ).fetchone()
            if row is None:
                report.line(False, f"job {job}", "never ran")
                continue
            report.line(row[0] == "ok" and row[1] <= limit, f"job {job}", f"{row[0]}, {row[1]:.0f} min ago")
        age = conn.execute("select extract(epoch from now() - max(ts)) / 60 from live_obs").fetchone()[0]
        report.line(age is not None and age < 60, "newest observation", f"{age:.0f} min old")
    finally:
        conn.close()
    raw_dir = env.get("RAW_DIR") or "data/raw"
    prefix = f"{today:%Y/%m/%d}/"
    if raw_store.is_gcs(raw_dir):
        bucket, base = raw_gcs.split_url(raw_dir)
        blobs = raw_gcs.storage_client().list_blobs(bucket, prefix=raw_gcs.object_name(base, prefix))
        count = sum(1 for blob in blobs if str(blob.name).endswith(".json.gz"))
    else:
        root = Path(raw_dir) if Path(raw_dir).is_absolute() else REPO_ROOT / raw_dir
        count = sum(1 for _ in (root / prefix).glob("*/*.json.gz"))
    report.line(count > 0, "raw snapshots of today", f"{count} objects")


def secrets(report: Report, env: dict[str, str], bodies: list[str]) -> None:
    values = [env[name] for name in SECRET_NAMES if env.get(name)]
    report.line(len(values) == len(SECRET_NAMES), "all five secret names are in the env file")
    hit = any(value in body for value in values for body in bodies)
    report.line(not hit, "served pages and API bodies", "no match" if not hit else "A SECRET IS SERVED")
    static = REPO_ROOT / "app" / "web" / ".next" / "static"
    if static.is_dir():
        hit = False
        for path in static.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                hit = hit or any(value in text for value in values)
        report.line(not hit, "app/web/.next/static", "no match" if not hit else "A SECRET IS IN THE BUNDLE")
    else:
        report.line(False, "app/web/.next/static", "no build output; run `npm run build` first")
    hit = False
    for value in values:
        # `-e` takes the pattern from the argument list of a child process; nothing is echoed.
        found = subprocess.run(
            ["git", "grep", "-q", "-F", "-e", value], cwd=REPO_ROOT, capture_output=True, check=False
        )
        hit = hit or found.returncode == 0
    report.line(not hit, "git grep", "no match" if not hit else "A SECRET IS TRACKED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify")
    parser.add_argument("url")
    parser.add_argument("--env-file", default=".env.cloud")
    args = parser.parse_args(argv)
    path = Path(args.env_file) if Path(args.env_file).is_absolute() else REPO_ROOT / args.env_file
    if not path.exists():
        sys.exit(f"missing env file: {args.env_file}")
    env = {name: value for name, value in dotenv_values(path).items() if value}
    for name in ("DATABASE_URL", "ADMIN_TOKEN"):
        if name not in env:
            sys.exit(f"missing {name} in {args.env_file}")
    now = datetime.now(KST)
    report = Report()
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=30, follow_redirects=False) as client:
        bodies = site(report, client, env, f"{now:%Y-%m-%d}")
    data(report, env, now)
    secrets(report, env, bodies)
    print(f"{report.failed} failed")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
