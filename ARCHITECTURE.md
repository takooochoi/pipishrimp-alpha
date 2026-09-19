# PipiShrimp Alpha — public architecture notes

```text
official/public source candidates
            |
            v
bounded parsing and normalization
            |
            v
local human-review boundary
            |
            v
read-only FastAPI API (sample-backed demo)
            |
            v
React Native / Expo Android app
            |
            v
Seeker / supported Android wallet via MWA
```

## Product boundary

The Alpha is a decision-support experience, not an execution or custody
system. The app displays structured opportunity information and a read-only
wallet identity state. It has no transaction-signing, transfer, trading,
staking, delegation, or key-custody path.

## Evidence boundary

The backend keeps source provenance, evidence labels, normalized deadlines and
costs, and a manual-review state for source candidates. Candidates begin as
not publishable. The public demo endpoint remains backed by clearly labelled
sample fixtures.

## Technology

- Mobile: React Native, Expo custom development build, TypeScript, and the
  Solana Mobile Wallet Adapter through the wallet UI package.
- Backend: Python 3.12, FastAPI, Pydantic, and a small repository interface.
- Tests: pytest for the backend and Vitest for the mobile utility surface.

The public package intentionally omits private infrastructure, deployment
configuration, operational runbooks, governance records, financial records,
risk registers, and local runtime data.
