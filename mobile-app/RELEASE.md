# Android Release Build

This project uses the native Android Gradle release task to build a standalone APK. Release builds embed the JavaScript bundle into the APK through the existing Expo/React Native Gradle configuration, so the installed app does not depend on Metro or a development server.

## Release keystore

The local release keystore was generated with Java `keytool` and is stored at:

```text
mobile-app/android/app/mkjewels-release.keystore
```

Generation command shape:

```powershell
keytool -genkeypair -v -storetype PKCS12 -keystore android\app\mkjewels-release.keystore -alias mkjewels-release -keyalg RSA -keysize 2048 -validity 10000
```

The keystore file is intentionally ignored by git. The signing passwords are stored locally in:

```text
mobile-app/android/keystore.properties
```

That file is also intentionally ignored by git.

Required `android/keystore.properties` keys:

```properties
KEYSTORE_FILE=app/mkjewels-release.keystore
KEYSTORE_PASSWORD=<keystore password>
KEY_ALIAS=mkjewels-release
KEY_PASSWORD=<key password; for this PKCS12 keystore, use the same value as KEYSTORE_PASSWORD>
```

Alternatively, set these environment variables before building:

```powershell
$env:MKJEWELS_ANDROID_KEYSTORE_FILE = "app/mkjewels-release.keystore"
$env:MKJEWELS_ANDROID_KEYSTORE_PASSWORD = "<keystore password>"
$env:MKJEWELS_ANDROID_KEY_ALIAS = "mkjewels-release"
$env:MKJEWELS_ANDROID_KEY_PASSWORD = "<key password; for this PKCS12 keystore, use the same value as MKJEWELS_ANDROID_KEYSTORE_PASSWORD>"
```

## Critical backup requirement

Back up both `mobile-app/android/app/mkjewels-release.keystore` and its passwords somewhere safe outside this repo, such as a password manager plus a cloud backup.

If this keystore file or its passwords are lost, future APKs signed with a different key cannot cleanly install as updates over APKs signed with this key. Users would have to uninstall the old app first and install the replacement as a separate fresh install, which can lose local app data.

## Build a release APK

After code changes, run:

```powershell
cd mobile-app\android
.\gradlew.bat assembleRelease --no-daemon
```

The output APK is written to:

```text
mobile-app/android/app/build/outputs/apk/release/app-release.apk
```

## Publish APK download link

The production Flask backend serves the Android APK from this exact server path:

```text
/home/ubuntu/mk-jewels-store-sales/mobile-app/android/app/build/outputs/apk/release/app-release.apk
```

After each new release build, manually copy the rebuilt APK to that path on the production server before sharing the download link. From a local PowerShell terminal in the repo root, run:

```powershell
scp mobile-app\android\app\build\outputs\apk\release\app-release.apk ubuntu@store.mkjewels.net:/home/ubuntu/mk-jewels-store-sales/mobile-app/android/app/build/outputs/apk/release/app-release.apk
```

Once copied and the backend route is deployed, the direct download URL is:

```text
https://store.mkjewels.net/download/mkjewels-app.apk
```
