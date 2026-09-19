# PipiShrimp Alpha mobile

Android-first React Native + Expo custom development build for `BCOP-CODEX-0002`.

## Scope

- Opportunity feed, category/risk filters, and opportunity detail.
- FastAPI-backed sample data with explicit `SAMPLE DATA` labels.
- MWA connect/disconnect and truncated public address only.
- No balances, signatures, transfers, swaps, staking, delegation, or automated trading.

## Local commands

From this directory:

```powershell
npm ci
npm run lint:check
npm run build
npm test
npm run android
```

`npm run android` generates and installs the Android custom development build. Expo Go is not supported because MWA requires native Kotlin modules.

## CLOCK IN submission APK

Run the following from this directory after `npm ci` to produce the functional Seeker/Android APK used for the demo. The `EXPO_PUBLIC_API_BASE_URL` value is embedded while Metro creates the release bundle; it is intentionally a public read-only API base, not a credential.

```powershell
npm run lint:check
npm test
npm run build
$env:EXPO_PUBLIC_API_BASE_URL = 'https://api.pipishrimp.online'
Push-Location android
.\gradlew.bat assembleRelease -PreactNativeArchitectures=arm64-v8a
Pop-Location
```

The artifact is written to `android/app/build/outputs/apk/release/app-release.apk`. The build uses the generated local debug keystore only to create a functional test/demo artifact; do not add a production signing keystore or commit the APK. Record the file size and SHA-256 before handing the artifact to the Owner.

Install the APK on a connected Android/Seeker device with `adb install -r android/app/build/outputs/apk/release/app-release.apk`, then launch it without Expo Go. Complete the bounded connect, fresh reject/cancel, reconnect, truncated public-address, and disconnect smoke. No signing, transaction, transfer, balance, or Seed Vault operation is part of this demo.

Set `EXPO_PUBLIC_API_BASE_URL` before starting Metro. The default `http://10.0.2.2:8000` reaches a backend running on the host from an Android emulator. A physical Seeker needs the host LAN IP, for example `http://192.168.1.10:8000`.

The app reads only the public address returned by `useMobileWallet()`. It never requests or stores seed phrases, private keys, keystores, passwords, signatures, or transaction payloads.
