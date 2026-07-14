# MK Jewels Android App Shell

Phase 1 wraps the existing production recorder web app in a Capacitor Android
shell. It does not change `recorder.html`, WebSocket capture, or recording
logic.

## What Gets Wrapped

The salesperson recorder is a standalone Flask-served HTML page:

- Source: `mk-jewels-assistant/dashboard/recorder.html`
- Route: `GET /recorder` in `mk-jewels-assistant/dashboard/server.py`
- Production URL: `https://store.mkjewels.net/recorder`

It is not part of the `dashboard-ui` Next.js build. `dashboard-ui/` is the
manager dashboard app served separately at the site root.

For Phase 1, Capacitor should be initialized in this `mobile-app/` directory
and configured to load the live recorder page:

```ts
server: {
  url: "https://store.mkjewels.net/recorder",
  cleartext: false,
}
```

This keeps the Android shell focused on validating that the existing live
recorder flow loads and functions in a native WebView before Phase 2 adds
native recording support.

## Required Local Toolchain

The Android build machine needs:

- Node.js, npm, and npx
- Java JDK with `java` and `javac` available on `PATH`
- Android SDK command-line tools
- `ANDROID_HOME` or `ANDROID_SDK_ROOT` pointing to the SDK directory
- `sdkmanager` and `adb` available on `PATH`

Do not install Android Studio from this repo. If the IDE is missing, install it
manually. If only command-line SDK tools are missing, install Android SDK
Command-line Tools, then use `sdkmanager` to install the Android platform and
build tools required by the generated Capacitor project.

## Phase 1 Setup Commands

Run these commands from the repository root after the Android toolchain is
available:

```powershell
cd mobile-app
npm.cmd init -y
npm.cmd install @capacitor/core @capacitor/cli @capacitor/android
npx.cmd cap init "MK Jewels Recorder" "com.mkjewels.recorder" --web-dir .
npx.cmd cap add android
```

Then edit `capacitor.config.ts` so the app loads the live recorder URL:

```ts
import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.mkjewels.recorder",
  appName: "MK Jewels Recorder",
  webDir: ".",
  server: {
    url: "https://store.mkjewels.net/recorder",
    cleartext: false,
  },
};

export default config;
```

The app id `com.mkjewels.recorder` is the current recommended default. Confirm
it before production release if MK Jewels already has a reserved Android package
namespace.

## Build Debug APK

After `npx.cmd cap add android` succeeds:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Expected debug APK path:

```text
mobile-app/android/app/build/outputs/apk/debug/app-debug.apk
```

Install it on a test phone with:

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Open the app and confirm it loads `https://store.mkjewels.net/recorder`, store
selection works, salesperson auth works, and the existing recorder UI reaches
the recording screen.

## Phase 2 Scope

Phase 2 will add native Android recording support using a foreground service
with microphone access. That phase is expected to add Android-native code and
permissions such as:

- `android.permission.FOREGROUND_SERVICE`
- `android.permission.FOREGROUND_SERVICE_MICROPHONE`
- A foreground service with `android:foregroundServiceType="microphone"`

Phase 2 should bridge native microphone capture into the existing backend flow
without relying on browser-tab `getUserMedia()` while the screen is off.
