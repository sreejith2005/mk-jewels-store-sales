# MK Jewels Demo Startup

## Quick Reference: Dev → Production

```
MAKE CHANGE:
  → Edit locally → pytest passes → npm build passes → git push

DEPLOY:
  → ssh into server → git pull origin main
  → pip install (if requirements changed)
  → npm run build + pm2 restart (if frontend changed)
  → sudo systemctl restart mkjewels-backend.service (if backend changed)

CHECK LOGS:
  → sudo journalctl -u mkjewels-backend.service -n 50 --no-pager
  → pm2 logs mkjewels-dashboard

CHECK SERVICES:
  → sudo systemctl status mkjewels-backend.service
  → pm2 status
```

---

> [!IMPORTANT]
> **Windows Port Note:** On this machine, Windows (`svchost`) reserves ports `5000` and `8765`. The `.env` file already overrides these to `FLASK_PORT=5001` and `WS_PORT=8766`. Do not change them back.

---

## Option A: Manager Dashboard (Flask API + Next.js UI)

Open **two separate** PowerShell windows.

### Window 1 — Backend Flask API

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\mk-jewels-assistant
$env:FLASK_APP = "dashboard.server:app"
..\venv\Scripts\flask.exe run --host 127.0.0.1 --port 5001 --no-debugger --no-reload
```

Leave this window open. Quick health check (from a new window):

```powershell
Invoke-RestMethod http://127.0.0.1:5001/api/debug
```

Expected response: `{"sessions": 2, "events": 10}` (numbers may vary).

### Window 2 — Dashboard UI (Next.js)

> [!NOTE]
> Use `npm.cmd` instead of `npm` — PowerShell blocks `npm.ps1` by default on this machine.

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\dashboard-ui
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:5001"
npm.cmd run dev
```

Leave this window open, then open the dashboard in your browser:

```
http://localhost:3000
```

### Stop Option A

Press `Ctrl+C` in both windows. If a process is stuck:

```powershell
netstat -ano | Select-String ":3000|:5001"
Stop-Process -Id <PID>
```

---

## Option B: Phone Recorder Demo (Live Capture)

This starts Flask on port `5001` AND the WebSocket server on port `8766` (set via `.env`). Run everything from the backend folder:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\mk-jewels-assistant
..\venv\Scripts\python.exe main.py
```

When prompted:

```
Run mode: (1) Live mic  (2) Test with audio file  (3) Start dashboard server  (4) Generate end-of-day report  (5) Start live phone capture: 5
```

Enter `5` and press Enter. The app will print a URL like:

```
Open this URL on your phone: http://192.168.x.x:5001/recorder?name=YourName
```

Open that URL on your phone (must be on same Wi-Fi). Keep this terminal running while recording.

> [!NOTE]
> If you see `OSError: [Errno 10048]` (address already in use), another instance is already running. Find and kill it:
> ```powershell
> netstat -ano | Select-String ":5001|:8766"
> Stop-Process -Id <PID>
> ```
