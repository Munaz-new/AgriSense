# AgriSense Phase 11: security verification and Android release preparation

Project title: **AgriSense: Plant Disease Detection and Health Monitoring Using Hybrid CNN-Transformer Architecture**.

## Phase 10 verification and public deployment decision

No Phase 10 commit, branch, or implementation was present in the inspected Git history or worktree when this phase began. The prior origin/main commit was `767e011` (Phase 9). Source inspection confirms the earlier security finding remains: there is no identity provider, authentication middleware, `user_id`/`owner_id` column, or user ownership check. Schema version 3 has only the shared `plants` and `observations` tables. Existing records have no owner attribution, and no safe owner migration exists because their authors cannot be inferred.

The API remains a single shared journal. Anonymous callers can list and read plants/observations and create plants and observations; there is no cross-account boundary to test. Development mode serves images under `/uploads`. The Phase 9 production-mode config hides that route, but it does not authenticate journal API routes. Consequently **public deployment and public Android API configuration are blocked**. Do not put a shared API key in the mobile binary. No cloud service was contacted for deployment and no credentials were created.

## Python 3.14 diagnosis

Python itself did not produce a segmentation fault or core dump in this checkout. The reproducible failure is a **TestClient startup hang** in `model/.venv`, before app lifespan starts: its Python 3.14.7 environment has FastAPI 0.135.1, Starlette 1.7.0, AnyIO 4.15.1 and httpx 0.28.1. The same minimal FastAPI `TestClient` startup succeeds in `backend/.venv`, which has the same Python/FastAPI/AnyIO/httpx but Starlette 1.6.0. This isolates the observed hang to the differing Starlette/TestClient runtime combination; it does not establish a Python interpreter crash.

The serving and production dependency sets now pin Starlette 1.6.0. Backend tests must run from `backend/` using `backend/.venv`, the supported serving environment. Model inference tests run in `model/.venv` and do not use the hanging `TestClient` path. A clean reinstall of the combined inference requirements was not performed in this phase.

## Android release configuration and build result

Expo SDK resolves to 57.0.26 (React Native 0.86.3). The app now declares package ID `com.munaz.agrisense`, version code 1, and `android.permission.CAMERA`; the generated manifest requests camera access, keeps legacy gallery storage permissions capped at API 32, and removes audio recording permission. Expo Go scripts remain unchanged. The package ID is a permanent Android install/update identity; confirm it is the desired namespace and store availability before external publication.

`frontend/plugins/withReleaseSigning.js` removes Expo's unsafe default of signing a release variant with the debug keystore. Gradle release signing is configured only when the four private `AGRISENSE_ANDROID_*` keystore variables are supplied. With no credentials, Gradle produces an unsigned release APK, which is not installable as a distributable app. Do not save the signing key/passwords in Git, `.env`, Expo public variables, or the APK.

This environment has Java/Javac 21.0.12, Android platforms 35 and 36, build-tools 35.0.0/36.0.0/37.0.0, and NDK 28.2.13676358. The Android SDK directory is read-only here, so `sdkmanager --list_installed` cannot create its bin directory. ADB cannot open its local server socket in this sandbox, and no connected device was verified.

**No APK was produced.** Expo prebuild succeeded and generated the Android project. The generated Gradle wrapper requires Gradle 9.3.1, which is not cached; downloading from `services.gradle.org` timed out even outside the sandbox. The cached Gradle 9.1.0 run also stopped offline because the `org.gradle.toolchains.foojay-resolver-convention:1.0.0` plugin is not cached. No build outputs should be treated as an APK. A production API host is also intentionally unavailable until authentication and ownership are implemented.

After a secure authenticated HTTPS API is approved, the local sequence is:

```sh
cd /home/munaz/Projects/AgriSense/frontend
npm ci
npx expo prebuild --platform android --clean
export EXPO_PUBLIC_API_URL='https://your-authenticated-api.example'
# Enter these interactively or load them from a protected secret store; do not
# put passwords in shell history, app config, Expo public variables, or Git.
read -r -p 'Keystore file path: ' AGRISENSE_ANDROID_KEYSTORE
read -r -p 'Key alias: ' AGRISENSE_ANDROID_KEY_ALIAS
read -r -s -p 'Keystore password: ' AGRISENSE_ANDROID_STORE_PASSWORD; printf '\n'
read -r -s -p 'Key password: ' AGRISENSE_ANDROID_KEY_PASSWORD; printf '\n'
export AGRISENSE_ANDROID_KEYSTORE AGRISENSE_ANDROID_KEY_ALIAS
export AGRISENSE_ANDROID_STORE_PASSWORD AGRISENSE_ANDROID_KEY_PASSWORD
./android/gradlew assembleRelease
```

The placeholder API hostname above must be replaced before building; Expo public variables are bundled into the APK. Obtain Gradle 9.3.1 and missing Maven artifacts through the official wrapper/repositories on a network-enabled machine. If SDK packages are absent there, install API 36, Android Build Tools 36.0.0, NDK 28.2.13676358, and current Android command-line tools through Android Studio SDK Manager. Keep the SDK location writable by the build user. Protect and back up the release keystore separately; losing it prevents upgrades under the same app identity.

## Backend deployment readiness

The Phase 9 RAM measurement remains about 1.9 GiB peak RSS for both model components together; begin any future CPU host evaluation at 4 GiB and one worker. Keep SQLite and images on one durable single-writer volume. The Dockerfile and production settings are preparation only and the Docker image itself was not built. Neither those settings nor TLS at a host remove the authentication/ownership blocker. The detailed resource measurements and hosting comparison remain in [Phase 9 readiness](phase9-deployment-readiness.md).

## Verification performed

- Backend security/API suite: 153 passed, 5 skipped (Python 3.14.7, `backend/.venv`; two upstream deprecation warnings).
- Model inference/pipeline suite: 118 passed (`model/.venv`).
- Frontend: 127 passed, 0 failed; includes camera upload/history and Android release-config regressions.
- TypeScript: `npm run typecheck` passed.
- Expo web export: passed; Expo Android JavaScript bundle export: passed. These are bundle exports, not native APK builds.
- TypeScript check and supported Expo web/Android exports: run after final config changes.
- Expo Android prebuild: passed, including generated camera permission and environment-driven signing configuration.
- Android APK: not built; no artifact was created or validated.
- Physical phone: not retested in Phase 11. The five camera-to-history checks are the project owner's earlier report, not Phase 11 device evidence.

## Remaining before independent use and release

1. Implement real sign-in/session handling and ownership enforcement for every plant, observation, progression, and image request; create an explicit policy for existing shared records before migrating them.
2. Add and pass cross-account read/write/photo-denial tests, private image delivery, rate limiting, and authentication failure/revocation tests.
3. Decide and verify the final Android package ID, app signing key custody, HTTPS API domain, backups/restore, and operational monitoring.
4. Build the signed APK on a machine with the required Gradle/plugin dependencies, then install it on an Android device and repeat camera, upload, suitability, disease result, and history persistence checks against the authenticated API.
