# KeepWise

See what you keep at month end. KeepWise finds subscriptions you don't use, suggests cheaper swaps, keeps promo codes, plans your budget in three envelopes, and splits bills with friends.

## Try it

- **Any phone (free):** open the web app at https://chillwillpill.github.io/keepwise/.
  - iPhone: open it in Safari → Share → **Add to Home Screen**.
  - Android: open it in Chrome → menu → **Install app**.
- **Android app:** download `keepwise.apk` from the **KeepWise test build** release on this page, open it on your phone, and allow installs when asked.

Your data stays on your phone. Nothing is sent to a server.

## How this repo works

- `src/app.html` is the whole app (one file, no framework).
- `scripts/build.py` turns it into the installable web app in `www/` (manifest, icons, offline support).
- `android/` and `ios/` are the native shells (Capacitor) that load `www/`.
- `tests/test_app.py` runs 28 end-to-end tests in a real browser.
- Every push to `main` runs the tests, builds the Android APK, and publishes the web app (`.github/workflows/build.yml`).

Run locally:

```
python3 scripts/build.py
pip install playwright && python -m playwright install chromium
python3 tests/test_app.py www/index.html
```

## iPhone app (App Store)

Building the iOS app needs a Mac with Xcode and an Apple Developer account ($99/year) for TestFlight or the App Store. Until then, iPhone users install the web app from Safari (see above); it runs full screen with its own icon.
