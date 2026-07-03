## PRODUCTION SAFETY PREAMBLE — READ BEFORE MAKING ANY CHANGES

This project is live in production at https://store.mkjewels.net

Production environment:
- AWS EC2 g4dn.xlarge, Mumbai ap-south-1
- PIPELINE_MODE=production (IndicConformer STT + Qwen3 via Ollama)
- Supabase Postgres via session pooler (POSTGRES_URL in .env)
- Nginx reverse proxy, HTTPS via Cloudflare
- Flask backend on port 5000, Next.js on port 3000, WebSocket on port 8765
- 23+ pytest tests must pass after every change
- Next.js build must pass after every frontend change

RULES YOU MUST FOLLOW:

1. NEVER modify .env or .env.example with real credentials.
   Real credentials only exist on the server, not in git.

2. NEVER change PIPELINE_MODE defaults in config.py.
   Local dev uses demo mode. Production uses production mode via server .env.

3. NEVER change DB schema without a migration-safe approach.
   All schema changes must use ALTER TABLE IF NOT EXISTS or equivalent
   so existing Supabase data is preserved.

4. NEVER remove or rename existing API routes or change their response shapes.
   The production frontend depends on the exact current API contract.

5. NEVER change the WebSocket audio streaming code in recorder.html
   unless explicitly asked. Any break here stops all recording in production.

6. NEVER change authentication logic for existing routes without explicit instruction.
   /api/auth/salesperson, /api/admin/set_pin, and basic auth middleware are
   production-critical.

7. ALWAYS run pytest after backend changes:
   cd mk-jewels-assistant && ..\venv\Scripts\python.exe -m pytest tests/ -v
   All tests must pass.

8. ALWAYS run npm run build after frontend changes:
   cd dashboard-ui && npm run build
   Must pass with no errors.

9. ALWAYS list every file changed at the end of your response.

10. If a change requires a server-side action (new env var, new dependency,
    model download, DB migration), call it out explicitly in a section called
    DEPLOYMENT NOTES so it is not missed when pulling to production.

12. DEPLOYMENT NOTES must include the EXACT pip install command if any new
    package was added to requirements.txt. Format:
       source venv/bin/activate && pip install -r requirements.txt
    Do not just say 'install new dependencies' — give the exact command.

Local dev uses SQLite (sessions.db). Production uses Supabase.
Do not run seed.py without explicit instruction — data is already in Supabase.

Current test count: 29 passing. Do not break existing tests.

