# OBSIDIAN MM - Linux Server Deployment

## Quick Start

```bash
# Clone repository
cd /home/safrtam
git clone https://github.com/Maeshowe/obsidian_mm.git
cd obsidian_mm

# Run deployment script
chmod +x scripts/deploy_linux.sh
./scripts/deploy_linux.sh

# Configure API keys
nano .env
```

## Systemd Setup

### 1. Install systemd files

```bash
# Daily data collection
sudo cp scripts/obsidian-daily.service /etc/systemd/system/
sudo cp scripts/obsidian-daily.timer /etc/systemd/system/

# Dashboard web service (port 8502)
sudo cp scripts/obsidian-dashboard.service /etc/systemd/system/

sudo systemctl daemon-reload
```

### 2. Enable and start services

```bash
# Enable daily data collection timer
sudo systemctl enable obsidian-daily.timer
sudo systemctl start obsidian-daily.timer

# Enable and start dashboard
sudo systemctl enable obsidian-dashboard
sudo systemctl start obsidian-dashboard
```

### 3. Verify

```bash
# Check timer status
sudo systemctl status obsidian-daily.timer
sudo systemctl list-timers --all | grep obsidian

# Check dashboard status
sudo systemctl status obsidian-dashboard

# Check logs
journalctl -u obsidian-daily.service -f
journalctl -u obsidian-dashboard.service -f
```

## Nginx Configuration (Multi-site)

Add to `/etc/nginx/sites-available/obsidian.ssh.services`:

```nginx
server {
    listen 80;
    server_name obsidian.ssh.services;

    location / {
        proxy_pass http://127.0.0.1:8502;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/obsidian.ssh.services /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# SSL with certbot
sudo certbot --nginx -d obsidian.ssh.services
```

## Port Allocation

| Service | Port | Domain |
|---------|------|--------|
| moneyflows | 8501 | https://moneyflows.ssh.services |
| obsidian | 8502 | https://obsidian.ssh.services |

## Schedule

Daily data collection runs **Mon-Fri at 21:00 UTC** (22:00 CET), after US market close.

## Manual Commands

```bash
cd /home/safrtam/obsidian_mm
source .venv/bin/activate

# Run daily pipeline manually
python scripts/run_daily.py SPY QQQ IWM DIA

# Check data collection status
python scripts/compute_baseline.py SPY --status

# Compute baseline (after 21+ days)
python scripts/compute_baseline.py SPY QQQ IWM DIA --local-only --force

# Run dashboard manually (for testing)
streamlit run obsidian/dashboard/app.py --server.port 8502
```

## Data Collection Timeline

| Day | Status |
|-----|--------|
| 1-21 | Collecting data |
| 21+ | Baseline automatically computed |

## Troubleshooting

```bash
# Check logs
tail -f /home/safrtam/obsidian_mm/logs/daily.log

# Test API keys
cd /home/safrtam/obsidian_mm
source .venv/bin/activate
python scripts/diagnose_api.py --ticker SPY

# Force run data collection now
sudo systemctl start obsidian-daily.service

# Restart dashboard
sudo systemctl restart obsidian-dashboard
```

## Git Pull Updates

```bash
cd /home/safrtam/obsidian_mm
git pull origin main
sudo systemctl restart obsidian-dashboard
```
