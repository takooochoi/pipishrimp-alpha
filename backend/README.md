# PipiShrimp Alpha backend

FastAPI read-only opportunity feed for `BCOP-CODEX-0002`. The repository is an in-memory sample fixture behind a small interface so PostgreSQL can be added later without changing the API contract.

All records are explicitly marked `is_sample: true` and `evidence_level: sample`; they are not verified campaign or reward claims.

## Local commands

```powershell
uv run --with-requirements requirements.txt python -m pytest -q
uv run --with-requirements requirements.txt python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The Android emulator reaches the host service at `http://10.0.2.2:8000`. A physical device needs `EXPO_PUBLIC_API_BASE_URL` set to the host's LAN address.

## API

- `GET /healthz`
- `GET /v1/opportunities?category=research&risk_level=low`
- `GET /v1/opportunities/{id}`

The BCOP Opportunity Score is the sum of six already-weighted components: Expected ROI (25), Evidence Quality (20), Capital Efficiency (15), AI Leverage (15), Strategic Value (15), and Risk (10). Risk is a risk-adjusted favorability score: higher points mean lower or better-controlled risk.

## Milestone 3 ingestion

The bounded official-source ingestion primitives, evidence labels, deterministic
deadline/cost normalization, and manual-review boundary are documented in
`docs/OPPORTUNITY_INGESTION.md` and implemented in `app/ingestion.py`. They are
not wired to external publication or execution.

## Local Milestone 3 operator workflow

The two configured source adapters are available through a bounded local CLI.
The default SQLite store is `backend/.runtime/review.sqlite3`; this runtime
directory is ignored by Git and contains normalized candidates plus review
audit records only.

```powershell
python -m app.cli ingest
python -m app.cli list --state needs_review
python -m app.cli show solana-mobile-clock-in-hackathon
python -m app.cli approve solana-mobile-clock-in-hackathon
python -m app.cli reject solana-mobile-builder-grants
python -m app.cli audit solana-mobile-clock-in-hackathon
```

Run these commands from `backend/`. Use `--db PATH` before the subcommand for a
different local SQLite file. `ingest` fetches only the fixed official URLs
through the bounded fetcher; it never writes to the public API repository,
publishes externally, or performs account, wallet, transaction, or payment
actions. `--update-pending` is required for an explicit update of an existing
unreviewed candidate.
