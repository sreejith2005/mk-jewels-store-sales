# MK Jewels Demo Startup

## Quick Reference: Dev to Production

```text
MAKE CHANGE:
  Edit locally -> pytest passes -> npm build passes -> git push

DEPLOY:
  ssh into server -> git pull origin main
  pip install (if requirements changed)
  npm run build + pm2 restart (if frontend changed)
  sudo systemctl restart mkjewels-backend.service (if backend changed)

CHECK LOGS:
  sudo journalctl -u mkjewels-backend.service -n 50 --no-pager
  pm2 logs mkjewels-dashboard

CHECK SERVICES:
  sudo systemctl status mkjewels-backend.service
  pm2 status
```

---

> [!IMPORTANT]
> Windows port note: on this machine, Windows (`svchost`) reserves ports `5000` and `8765`.
> The local `.env` overrides these to `FLASK_PORT=5001` and `WS_PORT=8766`.
> Do not change them back for local testing.

---

## Option A: Manager Dashboard (Flask API + Next.js UI)

Open two separate PowerShell windows.

### Window 1 - Backend Flask API

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\mk-jewels-assistant
$env:FLASK_APP = "dashboard.server:app"
..\venv\Scripts\flask.exe run --host 127.0.0.1 --port 5001 --no-debugger --no-reload
```

Leave this window open.

Health check from a new PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5001/api/health
```

Expected response in demo mode:

```json
{"pipeline":"demo","status":"ready"}
```

Manager login API check:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:5001/api/auth/manager `
  -ContentType "application/json" `
  -Body '{"password":"5500"}'
```

Expected response includes:

```json
{"success":true,"token":"..."}
```

Use the token to test a protected route:

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:5001/api/auth/manager `
  -ContentType "application/json" `
  -Body '{"password":"5500"}'

Invoke-RestMethod `
  -Uri http://127.0.0.1:5001/api/stores `
  -Headers @{ "X-Manager-Token" = $login.token }
```

Without `X-Manager-Token`, protected dashboard API routes should return `401 Unauthorized`.

### Window 2 - Dashboard UI (Next.js)

> [!NOTE]
> Use `npm.cmd` instead of `npm`; PowerShell can block `npm.ps1` on this machine.

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\dashboard-ui
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:5001"
npm.cmd run dev
```

Open the dashboard:

```text
http://localhost:3000
```

Sign in with the manager password from `mk-jewels-assistant\.env`.
The current local default is:

```text
5500
```

Dashboard auth is stored in browser `localStorage` under `mkj_manager_auth` for 8 hours.
Use the sidebar `Sign Out` button to clear it.

### Stop Option A

Press `Ctrl+C` in both windows. If a process is stuck:

```powershell
netstat -ano | Select-String ":3000|:5001"
Stop-Process -Id <PID>
```

---

## Option B: Phone Recorder Demo (Live Capture)

This starts Flask on port `5001` and the WebSocket server on port `8766` using `.env`.
Run everything from the backend folder:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\mk-jewels-assistant
..\venv\Scripts\python.exe main.py
```

When prompted:

```text
Run mode: (1) Live mic  (2) Test with audio file  (3) Start dashboard server  (4) Generate end-of-day report  (5) Start live phone capture:
```

Enter `5` and press Enter. The app will print a URL like:

```text
Open this URL on your phone: http://192.168.x.x:5001/recorder?name=YourName
```

Open that URL on your phone on the same Wi-Fi. Keep the terminal running while recording.

If you see `OSError: [Errno 10048]` (address already in use), another instance is already running:

```powershell
netstat -ano | Select-String ":5001|:8766"
Stop-Process -Id <PID>
```

---

## Test Before Pushing

Backend tests:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\mk-jewels-assistant
..\venv\Scripts\python.exe -m pytest tests/ -v
```

Frontend production build:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\dashboard-ui
npm.cmd run build
```

Frontend lint, when needed:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\dashboard-ui
npm.cmd run lint
```
