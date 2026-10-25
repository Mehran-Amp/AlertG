# Operations Runbook

## Health check + auto-restart (Phase 3E-2)

`scripts/health_check.py` polls `/health/deep` on the AlertG instance (port 8000) and:

- stays silent on HTTP 200
- alerts the admin on HTTP 503 or unexpected status (rate-limited to 1 / 30 min)
- auto-restarts the server via `./run_server.sh start` when the port is unreachable (rate-limited to 1 / 5 min)

### Install the cron entry

On `server360` (user `aisocial`, no sudo, no systemd):

```bash
crontab -e