# Findings — problems found outside the current SOW's scope

Append one entry per finding: date, where it was found, why it cannot be fixed now, what it touches (blast radius).
Never fix these off-scope; never drop them silently.

| Date | Found in | Finding | Why not now | Touches |
|---|---|---|---|---|
| 2026-09-29 | key check | The local `GOOGLE_MAPS_KEY` loads the Maps JavaScript API but its Google Cloud project has no billing (`BillingNotEnabledMapError`) | Cloud is SOW-MC; decide billing vs MapLibre there | `/map` (design spec §5.11), SOW-MC |
