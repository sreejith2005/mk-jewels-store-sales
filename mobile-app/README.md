# MK Jewels Native Recorder

Expo/React Native Phase 1 app for replacing the browser recorder with native
Android recording. The app mirrors the production recorder flow and streams
live 16 kHz mono 16-bit PCM to the existing WebSocket backend at
`https://store.mkjewels.net/ws`.

## Local Android Run

```powershell
$env:ANDROID_HOME="C:\Android"
$env:ANDROID_SDK_ROOT="C:\Android"
$env:JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"
$env:Path="$env:JAVA_HOME\bin;C:\Android\platform-tools;C:\Android\emulator;C:\Android\cmdline-tools\latest\bin;$env:Path"
npx.cmd expo run:android --device mkjewels_test
```

The generated Android manifest should include microphone foreground-service
permissions from `expo-audio` and `@siteed/audio-studio`.
