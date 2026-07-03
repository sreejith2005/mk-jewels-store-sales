# MK Jewels Demo Startup

# These is the quick reference step for demo -> Production
MAKE CHANGE:
  → Codex locally → pytest passes → npm build passes → git push

DEPLOY:
  → ssh into server
  → git pull origin main
  → pip install (if requirements changed)
  → npm run build + pm2 restart (if frontend changed)
  → sudo systemctl restart mkjewels (if backend changed)

CHECK LOGS:
  → sudo journalctl -u mkjewels -n 50 --no-pager
  → pm2 logs mkjewels-dashboard

CHECK SERVICES:
  → sudo systemctl status mkjewels
  → pm2 status
  → ollama list
  → curl http://localhost:11434/api/tags

Use these steps from PowerShell at the repo root:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool
```

## 1. Start the Backend API

Port `5000` is the default, but this machine may already have another Windows service listening on that port. For demos, use `5001`.

```powershell
$env:FLASK_APP = "dashboard.server:app"
.\venv\Scripts\flask.exe run --host 127.0.0.1 --port 5001 --no-debugger --no-reload
```

Leave this terminal open.

Quick health check from another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5001/api/debug
```

Expected shape:

```json
{"sessions":2,"events":10}
```

The numbers may differ depending on the current database.

## 2. Start the Dashboard UI

Open a second PowerShell window:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\dashboard-ui
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:5001"
npm run dev
```

Leave this terminal open.

## 3. Open the Demo

Open:

```text
http://localhost:3000
```

The dashboard should show the MK Jewels live store floor view, salesperson sessions, stats, and transcript events.

## Stop the Demo

Press `Ctrl+C` in both terminals.

If a process is stuck, find and stop it:

```powershell
netstat -ano | Select-String ":3000|:5001"
Stop-Process -Id <PID>
```

## Optional: Phone Recorder Demo

From the backend folder:

```powershell
cd C:\Users\MIS\Downloads\mkjewels-store-tool\mk-jewels-assistant
..\venv\Scripts\python.exe main.py
```

Choose:

```text
5
```

The app will print a recorder URL to open on the phone. Keep the terminal running while recording.
