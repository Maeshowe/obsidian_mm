#!/bin/bash
# OBSIDIAN MM - Daily data collection script
# Run after US market close (4 PM EST / 22:00 CET)
#
# Crontab setup (run: crontab -e):
#   0 22 * * 1-5 /Users/safrtam/SSH-Services/obsidian_mm/scripts/daily_cron.sh
#
# This collects data for SPY, IWM, DIA, QQQ

set -e

# Configuration
PROJECT_DIR="/Users/safrtam/SSH-Services/obsidian_mm"
LOG_DIR="${PROJECT_DIR}/logs"
TICKERS="SPY IWM DIA QQQ"
DATE=$(date +%Y-%m-%d)

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Activate virtual environment if exists
if [ -f "${PROJECT_DIR}/.venv/bin/activate" ]; then
    source "${PROJECT_DIR}/.venv/bin/activate"
fi

# Log start
echo "========================================" >> "${LOG_DIR}/daily.log"
echo "[${DATE}] Starting daily pipeline" >> "${LOG_DIR}/daily.log"

# Run pipeline for each ticker
cd "${PROJECT_DIR}"
python scripts/run_daily.py ${TICKERS} >> "${LOG_DIR}/daily.log" 2>&1

# Log completion
echo "[${DATE}] Pipeline completed" >> "${LOG_DIR}/daily.log"
echo "========================================" >> "${LOG_DIR}/daily.log"

# Check if we have enough data for baseline (after 21 days)
DAYS_COUNT=$(ls -1 data/processed/feature_history/SPY/*.json 2>/dev/null | wc -l | tr -d ' ')
if [ "${DAYS_COUNT}" -ge 21 ]; then
    echo "[${DATE}] Sufficient data (${DAYS_COUNT} days) - computing baselines..." >> "${LOG_DIR}/daily.log"
    python scripts/compute_baseline.py ${TICKERS} --local-only --force >> "${LOG_DIR}/daily.log" 2>&1
fi
