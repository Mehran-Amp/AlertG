# Release Gate — Device Test Matrix

Before publishing a new build, every row below must be marked **PASS** with
evidence attached (screenshot, logcat excerpt, or server journal state).

## 1. Build & Static Checks

| # | Check | How | PASS criteria | Evidence |
|---|---|---|---|---|
| 1.1 | Server tests | `python -m pytest tests -q` | all passed, 0 failed | last 5 lines of pytest output |
| 1.2 | Server import | `python -c "import server"` | no exception | terminal output |
| 1.3 | Flutter analyze | `flutter analyze` | 0 errors (warnings allowed) | last line of output |
| 1.4 | Flutter test | `flutter test` | All tests passed! | last 3 lines |
| 1.5 | GitHub Actions CI | Actions tab | latest run green (server + flutter) | URL + screenshot |
| 1.6 | Deep health | `curl -H "X-API-Key: ..." .../health/deep` | HTTP 200, `status: ok` | JSON body |

## 2. Device Matrix

Test each scenario on at least **two devices** (one Android 14, one Android 15+).
For iOS, if applicable, test on the latest stable iOS.

| # | Device / OS | Scenario | PASS criteria | Evidence |
|---|---|---|---|---|
| 2.1 | Android 14 | App open, foreground alert | banner + sound + TTS, journal `acked` < 5s | screenshot + logcat |
| 2.2 | Android 14 | App in background (recents) | banner + sound + TTS, journal `acked` | screenshot + logcat |
| 2.3 | Android 14 | Screen locked | banner + sound + TTS, journal `acked` | logcat |
| 2.4 | Android 14 | Airplane mode 2 min, then online | one banner (no duplicate sound), journal `acked` | logcat |
| 2.5 | Android 14 | App swiped from recents | banner + TTS (background isolate) | logcat |
| 2.6 | Android 14 | Doze mode 30 min, then alert | banner within 60s, journal `acked` or `unacked` | logcat + server journal |
| 2.7 | Android 15+ | Foreground service limit (dataSync) | service survives ≥ 6h, no system kill | `fgs.lifecycle` log |
| 2.8 | Android 15+ | Battery optimization ON | alert still delivered (or fallback to Telegram) | logcat + server journal |
| 2.9 | Android 15+ | Device reboot | service auto-starts, alerts delivered | logcat |
| 2.10 | Any | Dead FCM token (uninstall/reinstall) | journal `unacked` after ~5 min, Telegram fallback received | server journal + Telegram screenshot |
| 2.11 | Any | Server restart mid-ack-wait | alert not lost, journal `acked` after restart | server journal |
| 2.12 | Any | WebSocket + FCM simultaneously | exactly one banner (dedupe by `delivery_id`), no double sound | logcat |
| 2.13 | Any | WebSocket only (FCM disabled) | one banner via WS, ack over socket | logcat + server journal |
| 2.14 | Any | FCM only (WS disabled) | one banner via FCM, ack over HTTP | logcat + server journal |

## 3. Server-side Verification (after each device scenario)

| # | Check | How | PASS criteria |
|---|---|---|---|
| 3.1 | Delivery journal | `/api/status` → `delivery_unacked`, `delivery_acked` | values match scenario |
| 3.2 | Ack latency | `/api/status` → `ack_latency_avg_ms`, `ack_latency_p95_ms` | < 5000 ms for delivered |
| 3.3 | Outbox | `/api/outbox` | empty for successful deliveries |
| 3.4 | Deep health | `/health/deep` | HTTP 200, `status: ok` |
| 3.5 | Health check cron | `tail -20 ~/AlertG1/AlertG/health_check.log` | `✅ [health_check] ok` within last 10 min |

## 4. Rollback Readiness

| # | Check | PASS criteria |
|---|---|---|
| 4.1 | `ROLLBACK_PLAN.md` up to date | mentions latest catalog version + commit hash |
| 4.2 | Catalog rollback tested | `POST /api/admin/catalog/rollback` returns 200, version decremented |
| 4.3 | Snapshot exists | `ls catalog_snapshots/` shows a snapshot from the current version |

## 5. Sign-off

- [ ] All checks above PASS
- [ ] Evidence attached (screenshots, logcat, server journal)
- [ ] `ROADMAP.md` or release notes updated
- [ ] Version bumped in `pubspec.yaml` and `requirements.txt` (if applicable)

**Release approved by:** _______________  **Date:** _______________