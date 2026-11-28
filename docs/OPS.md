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
*/5 * * * * /home/aisocial/AlertG1/AlertG/scripts/run_health_check.sh >> /home/aisocial/AlertG1/AlertG/health_check.log 2>&1
```

## Phase 26 — Bourse Health Log, Outage Alert, Disk Guard & Log Rotation

### 26a (`IB-12c`): Periodic single-line Bourse health log
When `IRAN_BOURSE_ENABLED=true`, `app/markets/iran_bourse/monitor.py` emits one structured line every `IRAN_BOURSE_HEALTH_LOG_SECONDS` (default `180s`) to `server.log`:
```text
[IranBourse][health] market=OPEN gateway=ok(v0.2.2,ready=true,stale=false,age=18s) bridge=ok(errors=0) poller=running(leader=true,seq=42,watched=3,fails=0,stale=false)
```

### 26b (`IB-12d`): Market-hours gateway/bridge outage Telegram alert
During Tehran Bourse hours (Sat–Wed 08:30–19:00), if `gateway` or the Iranian `bridge` errors continuously for `>= IRAN_BOURSE_OUTAGE_ALERT_SECONDS` (default `600s` = 10 min), AlertG sends a Telegram message to `TELEGRAM_ADMIN_CHAT_ID` (repeat rate-limited to `1800s`) and a recovery notice once healthy again. Outside market hours, outage alerts are suppressed.

**Manual live test (during market hours):**
1. Stop the gateway: `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh stop`
2. Wait ~10–13 minutes (or set `IRAN_BOURSE_OUTAGE_ALERT_SECONDS=60` temporarily for a quick check) → verify admin Telegram receives `هشدار اختلال بورس ایران`.
3. Start the gateway again: `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh start` → verify admin Telegram receives `بازیابی سرویس بورس ایران`.

### 26c: Low-disk / user-quota alert & copytruncate log rotation
Each run of `scripts/health_check.py` (every 5 min via cron):
- Rotates `server.log` (>10 MB, keeps `.1.gz`..`.3.gz`), `health_check.log` (>5 MB, keeps `.1.gz`..`.2.gz`), and `~/tsetmc-gateway/gateway.log` (>5 MB, keeps `.1.gz`..`.2.gz`) in-place using gzip copytruncate.
- Checks both filesystem free space and `$HOME` usage against `DISK_QUOTA_MB` (default `3000` MB ≈ 2.93 GiB) and alerts `TELEGRAM_ADMIN_CHAT_ID` (max 1 per 6h) with the top 3 space consumers whenever free headroom drops below `DISK_MIN_FREE_MB` (default `512` MB).