# OBSIDIAN MM - Linux Server Deployment

## Quick Start

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/obsidian_mm.git /opt/obsidian_mm
cd /opt/obsidian_mm

# Run deployment script
chmod +x scripts/deploy_linux.sh
./scripts/deploy_linux.sh

# Configure API keys
nano .env
```

## Systemd Setup (Scheduled Data Collection)

### 1. Create service user

```bash
sudo useradd -r -s /bin/false obsidian
sudo chown -R obsidian:obsidian /opt/obsidian_mm
```

### 2. Install systemd files

```bash
sudo cp scripts/obsidian-daily.service /etc/systemd/system/
sudo cp scripts/obsidian-daily.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

### 3. Enable and start timer

```bash
sudo systemctl enable obsidian-daily.timer
sudo systemctl start obsidian-daily.timer
```

### 4. Verify

```bash
# Check timer status
sudo systemctl status obsidian-daily.timer

# List scheduled timers
sudo systemctl list-timers --all | grep obsidian

# Check logs
sudo journalctl -u obsidian-daily.service -f
```

## Schedule

The timer runs **Mon-Fri at 21:00 UTC** (22:00 CET / 16:00 EST), which is after US market close.

## Manual Commands

```bash
# Activate virtual environment
source /opt/obsidian_mm/.venv/bin/activate

# Run daily pipeline manually
python scripts/run_daily.py SPY QQQ IWM DIA

# Check data collection status
python scripts/compute_baseline.py SPY --status

# Compute baseline (after 21+ days)
python scripts/compute_baseline.py SPY QQQ IWM DIA --local-only --force

# Run dashboard
streamlit run obsidian/dashboard/app.py --server.port 8501
```

## Data Collection Timeline

| Day | Status |
|-----|--------|
| 1-7 | Collecting data |
| 8-14 | Collecting data |
| 15-21 | Minimum for baseline reached |
| 22+ | Full baseline available |

After 21 trading days (~4-5 weeks), the system will automatically compute baselines.

## Troubleshooting

### Check logs
```bash
tail -f /opt/obsidian_mm/logs/daily.log
```

### Test API keys
```bash
cd /opt/obsidian_mm
source .venv/bin/activate
python scripts/diagnose_api.py --ticker SPY
```

### Force run now
```bash
sudo systemctl start obsidian-daily.service
```
