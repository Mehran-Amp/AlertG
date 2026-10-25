#!/bin/bash
# Phase 3E-2: cron wrapper. Sets the pyenv PATH so `python3` and
# `run_server.sh` are found when cron invokes health_check.py
# (cron's default PATH does not include pyenv).
export PATH="/home/aisocial/.pyenv/versions/miniconda3-3.11-24.11.1-0/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/.." || exit 1
exec python3 scripts/health_check.py "$@"