Save this as **MK Jewels AWS Production Commands**.

---
# MAIN COMMANDS AFTER PUSHING (Can copy)

# SSH in
ssh -i "C:\Users\MIS\Documents\aws-keys\mkjewels-prod-key.pem" ubuntu@YOUR_ELASTIC_IP

# Pull latest code
cd ~/mk-jewels-store-sales
git pull origin main

# Rebuild frontend
cd dashboard-ui
npm install
npm run build

# Restart frontend
pm2 restart all

# Restart backend
cd ../mk-jewels-assistant
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart mkjewels-backend.service

# Verify everything is up
sudo systemctl status mkjewels-backend.service
pm2 status

# Watch backend come up (wait until you see "System ready - all models loaded")
sudo journalctl -u mkjewels-backend.service -f




# 1. SSH into AWS server

From **Windows PowerShell**:

```powershell
ssh -i "C:\Users\MIS\Desktop\aws keys\MK-Jewels-Store-Sales-prod-key.pem" ubuntu@store.mkjewels.net
```

Backup option using Elastic IP:

```powershell
ssh -i "C:\Users\MIS\Desktop\aws keys\MK-Jewels-Store-Sales-prod-key.pem" ubuntu@13.126.179.189
```

---

# 2. Go to project folder

After SSH login:

```bash
cd ~/mk-jewels-store-sales
```

Backend folder:

```bash
cd ~/mk-jewels-store-sales/mk-jewels-assistant
```

Dashboard folder:

```bash
cd ~/mk-jewels-store-sales/dashboard-ui
```

---

# 3. Activate Python backend venv

```bash
cd ~/mk-jewels-store-sales/mk-jewels-assistant
source venv/bin/activate
```

You should see:

```bash
(venv) ubuntu@...
```

---

# 4. Pull latest code from GitHub

```bash
cd ~/mk-jewels-store-sales
git status
git pull origin main
```

---

# 5. Backend deployment after code change

```bash
cd ~/mk-jewels-store-sales/mk-jewels-assistant
source venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
sudo systemctl restart mkjewels-backend.service
sudo systemctl status mkjewels-backend.service
```

Expected:

```text
active (running)
```

---

# 6. Backend logs

Latest logs:

```bash
journalctl -u mkjewels-backend.service -n 100 --no-pager
```

Live logs:

```bash
journalctl -u mkjewels-backend.service -f
```

Only errors:

```bash
journalctl -u mkjewels-backend.service --since "30 minutes ago" --no-pager | grep -iE "error|failed|exception|traceback|triage|stt|ollama|websocket"
```

---

# 7. Start / stop / restart backend

Restart backend:

```bash
sudo systemctl restart mkjewels-backend.service
```

Start backend:

```bash
sudo systemctl start mkjewels-backend.service
```

Stop backend:

```bash
sudo systemctl stop mkjewels-backend.service
```

Check backend:

```bash
sudo systemctl status mkjewels-backend.service
```

---

# 8. Dashboard deployment after code change

```bash
cd ~/mk-jewels-store-sales/dashboard-ui
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
nvm use 20
npm install
npm run build
pm2 restart mkjewels-dashboard
pm2 status
```

---

# 9. PM2 dashboard commands

Check dashboard:

```bash
pm2 status
```

Restart dashboard:

```bash
pm2 restart mkjewels-dashboard
```

Stop dashboard:

```bash
pm2 stop mkjewels-dashboard
```

Start dashboard:

```bash
pm2 start mkjewels-dashboard
```

Dashboard logs:

```bash
pm2 logs mkjewels-dashboard
```

Save PM2 startup state:

```bash
pm2 save
```

---

# 10. Nginx commands

Check Nginx config:

```bash
sudo nginx -t
```

Reload Nginx safely:

```bash
sudo systemctl reload nginx
```

Restart Nginx:

```bash
sudo systemctl restart nginx
```

Check Nginx status:

```bash
sudo systemctl status nginx
```

Edit Nginx config:

```bash
sudo nano /etc/nginx/sites-available/mkjewels
```

---

# 11. Ollama commands

Check Ollama status:

```bash
sudo systemctl status ollama
```

Restart Ollama:

```bash
sudo systemctl restart ollama
```

Check models:

```bash
ollama list
```

Test Qwen:

```bash
time ollama run qwen3:8b "Reply only with OK"
```

Check Ollama API:

```bash
curl http://localhost:11434/api/tags
```

---

# 12. Hugging Face commands

Check login:

```bash
hf auth whoami
```

Login again if needed:

```bash
hf auth login
```

Test IndicConformer load:

```bash
cd ~/mk-jewels-store-sales/mk-jewels-assistant
source venv/bin/activate
python transcription/indic_conformer_stt.py
```

Expected:

```text
IndicConformer load smoke test passed
```

---

# 13. Check running ports

```bash
ss -tulpen | grep -E "3000|5000|8765|80|443|11434"
```

Expected important ports:

```text
3000  Next.js dashboard
5000  Flask backend
8765  WebSocket
80    Nginx HTTP
443   Nginx HTTPS
11434 Ollama
```

---

# 14. Check disk space

```bash
df -h
```

Clean pip cache if needed:

```bash
pip cache purge
sudo apt clean
```

---

# 15. Production URLs

Dashboard:

```text
https://store.mkjewels.net
```

Recorder:

```text
https://store.mkjewels.net/recorder
```

API test:

```bash
curl -I https://store.mkjewels.net/api/stores
```

Recorder test:

```bash
curl -I https://store.mkjewels.net/recorder
```

---

# 16. Full normal deployment flow

Use this whenever Codex pushes new code:

```bash
ssh -i "C:\Users\MIS\Desktop\aws keys\MK-Jewels-Store-Sales-prod-key.pem" ubuntu@store.mkjewels.net

cd ~/mk-jewels-store-sales
git pull origin main

cd mk-jewels-assistant
source venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
sudo systemctl restart mkjewels-backend.service
sudo systemctl status mkjewels-backend.service

cd ~/mk-jewels-store-sales/dashboard-ui
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
nvm use 20
npm install
npm run build
pm2 restart mkjewels-dashboard
pm2 status

sudo nginx -t
sudo systemctl reload nginx
```

Then test:

```text
https://store.mkjewels.net
https://store.mkjewels.net/recorder
```

---

# 17. If server restarted / Spot interruption happened

SSH:

```powershell
ssh -i "C:\Users\MIS\Desktop\aws keys\MK-Jewels-Store-Sales-prod-key.pem" ubuntu@store.mkjewels.net
```

Check everything:

```bash
sudo systemctl status associate-eip.service
sudo systemctl status mkjewels-backend.service
sudo systemctl status ollama
pm2 status
sudo systemctl status nginx
```

If needed:

```bash
sudo systemctl restart ollama
sudo systemctl restart mkjewels-backend.service
pm2 restart mkjewels-dashboard
sudo systemctl reload nginx
```

---

# 18. Emergency rollback

```bash
cd ~/mk-jewels-store-sales
git log --oneline -5
git checkout <GOOD_COMMIT_HASH>
```

Restart backend:

```bash
cd ~/mk-jewels-store-sales/mk-jewels-assistant
sudo systemctl restart mkjewels-backend.service
```

Rebuild dashboard if needed:

```bash
cd ~/mk-jewels-store-sales/dashboard-ui
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
nvm use 20
npm run build
pm2 restart mkjewels-dashboard
```

Later fix GitHub properly with:

```bash
git revert <BAD_COMMIT_HASH>
git push origin main
```
