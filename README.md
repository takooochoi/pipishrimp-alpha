# PipiShrimp Alpha

PipiShrimp is an Android-first opportunity intelligence prototype for Solana
Seeker users. It turns an opportunity into a compact decision card with source,
evidence level, estimated capital, human time, deadline, risk, score, and a
recommended next action.

This repository contains the PipiShrimp Alpha source prepared for the
Solana Mobile CLOCK IN hackathon submission.

## What the Alpha demonstrates

- An Expo / React Native Android feed with category and risk filters.
- Opportunity detail pages with evidence, cost, time, deadline, risk, and
  BCOP Score fields.
- A FastAPI read-only API with an in-memory sample repository.
- Bounded source-ingestion and local manual-review code for official-source
  candidates.
- A Mobile Wallet Adapter (MWA) connect/disconnect experience that displays
  only a truncated public address.

## Sample-data disclosure

The public demo API is intentionally sample-backed at
`https://api.pipishrimp.online`. The records returned by
`/v1/opportunities` are in-memory fixtures and are marked `is_sample: true` and
`evidence_level: sample`. They are not live campaigns, verified rewards, or a
promise of returns. Review the source and current terms independently before
taking any action.

## Backend run path

Requirements: Python 3.12 and `uv` (or an equivalent virtual-environment
workflow).

From `backend/`:

```powershell
uv run --with-requirements requirements.txt python -m pytest -q
uv run --with-requirements requirements.txt python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API exposes:

- `GET /healthz`
- `GET /v1/opportunities`
- `GET /v1/opportunities/{id}`

The optional local ingestion/review CLI uses a SQLite file under the ignored
`.runtime/` directory. It stores normalized candidates and review audit rows
locally; it does not publish records, connect to a wallet, sign transactions,
move funds, or perform payment actions. Tests use committed fixtures and mocks,
not live campaign pages.

## Android / Seeker build path

Requirements: Node.js/npm, the Android SDK, Java/Gradle support, and a device
or emulator. MWA requires a native custom development build; Expo Go is not
sufficient.

From `mobile/`, use the current accepted build flow:

```powershell
npm ci
npm run lint:check
npm test
npm run build
$env:EXPO_PUBLIC_API_BASE_URL = 'https://api.pipishrimp.online'
Push-Location android
.\gradlew.bat assembleRelease -PreactNativeArchitectures=arm64-v8a
Pop-Location
```

The release artifact is written to
`android/app/build/outputs/apk/release/app-release.apk`. For a connected
Android/Seeker device, install it with:

```powershell
adb install -r android/app/build/outputs/apk/release/app-release.apk
```

Launch without Expo Go and complete the accepted smoke path: feed, category
filter, risk filter, detail, MWA connect, fresh reject/cancel, reconnect,
truncated public address, and disconnect. No signing, transaction, transfer,
balance, or Seed Vault operation is part of this demo.

The generated native `android/` directory, APK/AAB outputs, and local debug
keystore are intentionally not part of this source package. Do not add a
production signing keystore or commit any build artifact. Record the APK size
and SHA-256 separately when producing the Owner's local demo artifact.

For local backend development, the Android emulator default is
`http://10.0.2.2:8000`. Set `EXPO_PUBLIC_API_BASE_URL` to a reachable
development host instead of the public demo URL when testing a local backend.

## MWA read-only boundary

The Alpha calls MWA only for connect/disconnect state and reads the returned
public address for display. It does not request or store balances, signatures,
transactions, transfers, swaps, staking, delegation, seed phrases, private
keys, keystores, passwords, or 2FA secrets. Wallet signing authority remains
with the user-controlled wallet.

## Current limitations

- The public API is sample-backed rather than a live opportunity publication
  feed.
- The accepted submission build was tested on a physical Seeker; behavior on
  other Android devices or wallet implementations may differ.
- Source ingestion proposes candidates for review but does not publish them or
  execute external actions.
- This export contains source and tests only; it does not contain an APK,
  deployment configuration, private review data, logs, or production secrets.
- No retention, revenue, reward, or user-growth outcome is claimed.
