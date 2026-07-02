---
# MK Jewels Store Tool — Agent Instructions

## MANDATORY FIRST STEPS FOR EVERY SESSION

Before writing a single line of code, you must read these files in order:

1. Read CODEX_PREAMBLE.md — production safety rules, deployment notes format,
   git push requirement. Follow every rule in it without exception.

2. Read this file (agents.md) fully.

3. Read the specific files relevant to your task (listed per-task below).

## PROJECT OVERVIEW

Real-time AI sales coaching system for MK Jewels, a 5-branch jewelry retail
chain in Mumbai. Live at https://store.mkjewels.net

Two interfaces:
- Manager dashboard: https://store.mkjewels.net/ (Next.js, dark luxury UI)
- Salesperson recorder: https://store.mkjewels.net/recorder (mobile-first HTML)

## CODEBASE MAP

Backend (Python, Flask):
  mk-jewels-assistant/
    config.py               — all env vars and Config fields
    main.py                 — entry point, 5 modes
    dashboard/server.py     — all Flask API routes
    dashboard/recorder.html — salesperson mobile UI (3-screen flow)
    storage/db.py           — Database class, SQLite/Postgres dual mode
    storage/seed.py         — seeds 5 stores + 15 Bandra salespersons
    transcription/gemini_stt.py      — DEMO: Gemini STT+triage combined
    transcription/local_pipeline.py  — PRODUCTION: IndicConformer + Qwen3
    triage/qwen3_triage.py           — Qwen3 triage + KB context injection
    knowledge/objection_rules.json   — structured objection KB
    knowledge/product_facts.json     — product knowledge KB
    alerting/console_alert.py        — Telegram + Discord alerts
    tests/                           — 29 tests, all must pass

Frontend (Next.js):
  dashboard-ui/
    app/page.tsx      — full manager dashboard component
    app/globals.css   — brand tokens and CSS custom properties
    app/layout.tsx    — font setup
    public/brand/     — MK Jewels logos

Design system:
  .agents/skills/     — frontend design skills, read before any UI changes
  .agents/mk-jewels-DESIGN.md — brand colours, fonts, design language

## KEY ARCHITECTURAL DECISIONS (DO NOT CHANGE)

- PIPELINE_MODE=demo uses Gemini, PIPELINE_MODE=production uses local models
- Both pipelines expose identical function signature: transcribe_and_triage()
- No raw audio stored — transcripts only (DPDP compliance)
- SQLite for local dev, Postgres/Supabase for production (same db.py interface)
- Chunk duration: 3 seconds (CHUNK_DURATION_SECONDS=3 in .env)
- WebSocket port 8765, Flask port 5000, Next.js port 3000
- Production server: AWS EC2 g4dn.xlarge On-Demand, ap-south-1
- Production service: mkjewels-backend.service
- Supabase session pooler URL in POSTGRES_URL

## SALESPERSON AUTH FLOW

Screen 1: Select store
Screen 2a: Select name from dropdown
Screen 2b: Enter 4-digit PIN (OTP boxes, auto-advance)
  - If NO_PIN_SET: first-time setup flow (choose + confirm PIN)
  - If PIN matches: proceed, store 12hr localStorage auth
  - If PIN wrong: shake + "Incorrect PIN"
Screen 3: Recording screen with wake lock

## SIGNAL TYPES

objection_detected, price_concern, certification_question,
upsell_miss, knowledge_gap, intent_signal
Plus: script_deviation, factual_error, missed_script_response
Alert fires on medium or high priority AND knowledge_base_followed=false

## GIT WORKFLOW (MANDATORY AFTER EVERY SUCCESSFUL CHANGE)

After all tests pass and build passes:
  git add -A
  git commit -m "descriptive message"
  git push origin main

Then output DEPLOYMENT NOTES so the developer knows exactly what to
run on the server after git pull.

## DEPLOYMENT NOTES FORMAT (MANDATORY, end every response with this)

DEPLOYMENT NOTES:
- New env vars: <list or "none">
- New pip dependencies: <list or "none"> → run: pip install -r requirements.txt
- New npm dependencies: <list or "none"> → run: npm install
- DB migration: <describe or "none, runs automatically">
- Server commands after git pull:
    cd ~/mk-jewels-store-sales
    git pull origin main
    <any pip install commands>
    <any npm build commands>
    sudo systemctl restart mkjewels-backend.service
    <or pm2 restart if frontend changed>
- Services to restart: <mkjewels-backend.service / pm2 / both>
---
