# AgriSense phone-camera integration

Implementation and automated verification: October 13, 2026. Baseline `f9fd7a3`.
Physical Android/iOS and actual browser camera capture: **NOT TESTED**.

## Capture and analysis

Scan offers **Take Photo** and **Choose from Gallery** separately. Native Android
and iOS use the system camera through the existing `expo-image-picker`; the app
does not add an embedded native camera. A returned photo appears in the existing
preview with **Retake Photo**, **Cancel photo** and **Use photo — check file and
plant suitability**. Capture does not upload, diagnose or save automatically.
The explicit check uploads to the existing validation and suitability endpoints;
**Analyze tomato leaf and save** performs the existing screened disease-analysis
and observation save. Results, uncalibrated scores, null severity, records and
history continue to come from the backend.

Permission denial, unavailable camera, canceled capture and empty/invalid picker
results do not erase an existing photo. Retaking successfully replaces its preview
and clears the previous validation/suitability approvals. Cancel photo clears the
unsaved form, including its optional context; it does not delete saved records.
Rapid capture/save taps are guarded. During an uncertain save, retake, cancel and
gallery replacement stay locked; check history and retry the same request identity.
Backend connection failures retain the existing retry behavior and never generate
synthetic disease results.

## Packages and permissions

Installed Expo **57.0.24**, React Native **0.86.3**, image-picker **57.0.19**.
The installed Expo compatibility map specifies image-picker `~57.0.19`. No package,
lockfile or native configuration change was needed. The existing plugin already
has camera/photo descriptions and `microphonePermission: false`.

Native capture checks the camera permission first and requests it only when not
granted and the OS allows another prompt. Permanent denial explains how to allow
camera access in phone settings (for **Expo Go** when testing inside Expo Go).
Only still-image capture is requested; no microphone, location or additional
media-library permission request was added. The installed picker can require its
legacy storage permission on Android versions below 10; current Android uses the
camera permission for this capture path. Gallery behavior remains unchanged.

## Browser behavior

Take Photo uses `navigator.mediaDevices.getUserMedia` with `audio: false`, preferring
the rear camera when available. A modal live preview has visible **Capture photo**
and **Cancel camera** buttons. The frame is encoded as JPEG (longest side at most
2048 pixels) and returned to the normal preview. The backend still validates bytes.
Camera tracks stop immediately after copying a captured frame, on cancellation,
Escape, navigation/unmount, page exit, hidden tab or camera errors. Late permission
grants after cancellation are stopped too. Preview startup and photo encoding have
15-second limits; an unanswered permission prompt can always be canceled in the app.
Temporary photo URLs are released when the draft is replaced, canceled or unmounted.

Live camera requires a supported browser and a secure context: **HTTPS or localhost**.
`http://192.168.x.x:8081` on a phone is not localhost. This case displays an explicit
message and never silently opens the gallery. Use native Expo Go for the ordinary
LAN demo. A separate HTTPS browser setup must also make the API reachable securely
and configure its exact CORS origin; serving only the frontend over HTTPS does not
solve mixed-content API access. No hosting, tunnel or public deployment was added.

API references: [Expo ImagePicker](https://docs.expo.dev/versions/latest/sdk/imagepicker/),
[MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
[MDN stopping tracks](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop).

## Automated evidence and limits

- Frontend: **94 tests passed**, zero skipped. Covers native grant/denial/permanent
  denial, capture cancellation, invalid results, preview/retake/cancel, independent
  gallery selection, native/browser multipart payloads, analysis/retry identity,
  rapid taps and browser media/URL cleanup. Camera/DOM/OS behavior uses test doubles;
  no simulated photo is claimed as physical-camera evidence.
- TypeScript: `npm --prefix frontend run typecheck` passed.
- Backend: **62 tests passed**, zero skipped, covering image validation, serving
  contracts and observation records. The backend/model implementation is unchanged.
- Expo web, Android and iOS exports passed at
  `/tmp/agrisense-camera-export-2026-10-13`. These are bundles, not installable apps.
- Not rerun: full backend/model suites, real-checkpoint smoke, load tests, dependency
  audits or native prebuild. Prior submission evidence remains in the runbook.
- Not performed: actual browser camera/picker/reload walkthrough, physical Android
  or iOS tests, native APK/IPA builds. No APK is available; the previously identified
  missing Gradle 9.3.1 and NDK 27.1.12297006 prerequisites remain unresolved.

Reproduce from the repository root (backend tests require local socket access):

```bash
npm --prefix frontend test
npm --prefix frontend run typecheck
(cd backend && timeout 90s env OMP_NUM_THREADS=4 ../model/.venv/bin/python -m pytest -q -rs \
  tests/test_image_validation.py tests/test_real_integration.py tests/test_observation_records.py)
(cd frontend && CI=1 EXPO_OFFLINE=1 npx --no-install expo export --platform all \
  --output-dir /tmp/agrisense-camera-export-2026-10-13)
```

## Physical Android test — still to perform

1. Install an Expo Go version compatible with **SDK 57**. Connect the phone and
   workstation to the same trusted Wi-Fi. Find the workstation's LAN IPv4 address
   using `ip -4 addr show scope global` (not `127.0.0.1`).
2. Start the existing real backend in terminal 1:

   ```bash
   cd /home/munaz/Projects/AgriSense
   OMP_NUM_THREADS=4 model/.venv/bin/python -m uvicorn backend.app.main:app \
     --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
   ```

3. Start Expo in terminal 2. Replace the example address with that LAN address;
   this shell override leaves the existing `.env` file unchanged:

   ```bash
   cd /home/munaz/Projects/AgriSense/frontend
   EXPO_PUBLIC_API_URL=http://192.168.1.10:8000 npm start -- --lan --clear
   ```

4. On the phone, open `http://YOUR_LAN_IP:8000/health` to check connectivity and
   confirm tomato analysis and plant screening capabilities. Scan Expo's QR code
   in Expo Go. Allow local ports 8000 and 8081 through the workstation firewall if
   necessary. No CORS change is needed for native requests.
5. Add/select a tomato plant, open Scan, tap **Take Photo**, allow camera access,
   photograph a well-lit leaf and accept it in the system camera. Confirm the app
   preview is that fresh image. Retake once; cancel another capture and verify the
   previous preview remains. **Cancel photo** should clear the unsaved form.
6. Capture again, use the photo to check file and plant suitability, then choose
   **Analyze tomato leaf and save**. Verify the backend result, uncalibrated score,
   unavailable severity and saved photo/history. Also test **Choose from Gallery**.
7. Deny permission and retry; test persistent denial using Expo Go's app settings.
   Verify the explanation and that gallery selection still works. Try rapid taps,
   backend/network disconnection, checking saved history and retrying an uncertain
   save. Never start a new submission identity before checking whether it saved.
8. Record phone model, Android/Expo Go version, Git commit, backend checkpoint
   identity and results. Background/resume and process termination remain device
   checks: native drafts are session-only, and OS process death during capture is
   not automatically restored or reassigned to a plant.

For desktop browser testing, use the README loopback startup commands and open
`http://localhost:8081`. Separately test Allow/Deny, Capture/Cancel/Escape, retake,
switching tabs (camera must stop), gallery, draft recovery and analysis. None of
these manual checks should be marked complete based on automated doubles or exports.
