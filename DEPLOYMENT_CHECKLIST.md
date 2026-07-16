# MK Jewels Production Deployment Checklist

## Server Details
- Instance: AWS EC2 g4dn.xlarge On-Demand, ap-south-1
- Elastic IP: [fill in your elastic IP]
- Domain: https://store.mkjewels.net
- Service: mkjewels-backend.service
- SSH key: C:\Users\MIS\Documents\aws-keys\mkjewels-prod-key.pem

## Every Deployment — Run These Commands

### 1. SSH into server
ssh -i "C:\Users\MIS\Documents\aws-keys\mkjewels-prod-key.pem" ubuntu@YOUR_ELASTIC_IP

### 2. Pull latest code
cd ~/mk-jewels-store-sales
git pull origin main

### 3. Install any new Python dependencies (ALWAYS run this, even if unsure)
cd ~/mk-jewels-store-sales/mk-jewels-assistant
source venv/bin/activate
pip install -r requirements.txt

### 4. Install any new Node dependencies (run only if package.json changed)
cd ~/mk-jewels-store-sales/dashboard-ui
npm install

### 5. Rebuild Next.js (run only if frontend files changed)
cd ~/mk-jewels-store-sales/dashboard-ui
npm run build
pm2 restart mkjewels-dashboard

### 6. Restart backend (run if any Python file changed)
sudo systemctl restart mkjewels-backend.service

### 7. Verify everything is running
sudo systemctl status mkjewels-backend.service
pm2 status
ollama list
curl http://localhost:11434/api/tags

### 8. Check logs for errors
sudo journalctl -u mkjewels-backend.service -n 50 --no-pager

## Environment Variables on Server
Location: ~/mk-jewels-store-sales/mk-jewels-assistant/.env
To edit: nano ~/mk-jewels-store-sales/mk-jewels-assistant/.env
After editing: sudo systemctl restart mkjewels-backend.service

## Key Env Vars
PIPELINE_MODE=production
DEVICE=cuda
POSTGRES_URL=<supabase session pooler url>
GEMINI_API_KEY=<key> (needed even in production for daily reports)
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<group chat id>
CHUNK_DURATION_SECONDS=3
