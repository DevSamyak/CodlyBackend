# CpTracker API (FastAPI)

Server side of the Krono Flutter port. It does what Krono's `src/api/*` + `dataNormalizer.ts` did on-device:
fetches Codeforces, LeetCode, CodeChef, AtCoder, GeeksforGeeks, HackerRank and TopCoder data, normalises it
into one shape, and caches it. Clist credentials stay on the server.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add Clist creds only if you want TopCoder
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# docs: http://localhost:8000/docs
```

## Endpoints (all JSON, camelCase)
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/api/v1/profiles/{platform}/{handle}` | normalised `UnifiedProfile` |
| POST | `/api/v1/profiles/batch` | refresh many profiles; per-item `error` instead of failing the batch |
| GET | `/api/v1/profiles/{platform}/{handle}/rating-history` | points for the rating chart |
| GET | `/api/v1/profiles/{platform}/{handle}/contest-history?limit=20` | newest-first, with rating deltas |
| GET | `/api/v1/profiles/{platform}/{handle}/activity?tzOffsetMinutes=330` | `{ "YYYY-MM-DD": count }` for streaks/heatmap |
| GET | `/api/v1/contests?platforms=codeforces,atcoder` | merged schedule + per-platform `warnings` |
| GET | `/api/v1/potd` | LeetCode daily + GfG card |

Errors: `{"error": {"code": "not_found|bad_request|upstream_error", "message": "..."}}` with 404 / 400 / 502.

`platform` ∈ codeforces, leetcode, codechef, atcoder, geeksforgeeks, hackerrank, topcoder.

## Tests
`python -m unittest discover -s tests -t .` (no network or extra packages needed; providers are tested
against fixtures through a fake `HttpClient`).

## Notes
- CodeChef, AtCoder and GeeksforGeeks are HTML scrapers (same as Krono) and can break when those sites change layout.
- Caches are in-process (profiles 5 min, history/contests 10 min, POTD 1 h). Use one worker or add Redis to share.
- Hosting from a datacenter IP may get blocked by some of these sites; if so, route through a proxy.
