# Incident: Empty Sync Deleted Alerts (2026-10-26)

## Summary

On 2026-10-26, an empty `sync_user_alerts` call (mode=`mirror`) wiped the
server-side alert list for affected users. The client sent an empty list
before restoring the user's alerts from the cloud, and `sync_user_alerts`
treats an empty list in `mirror` mode as "delete everything absent."

Fixed in commit `a515fe0` (FIX-EMPTY-SYNC): `lib/main.dart` restores
alerts from the server **before** the first sync, and never pushes an
empty list.

## Impact

- Affected users: those who had cloud-synced alerts and whose local
  `alertRuleRepository` was empty at startup (fresh install, cleared data,
  or failed local load).
- Data loss: the server-side `ALERTS_DB` entries for those users were
  removed by `sync_user_alerts` (mode=`mirror`).
- Duration: until `a515fe0` was deployed.

## Timeline (UTC)

- 2026-10-26: incident observed (alerts missing after reinstall / clear-data).
- 2026-10-26: `a515fe0` committed (FIX-EMPTY-SYNC).
- 2026-10-26: deployed.

## Root Cause

`sync_user_alerts` (server) in `mirror` mode replaces the user's entire
alert list with the payload. An empty payload therefore deletes every
server-side alert for that user. The client called `syncAllRulesToServer`
at startup before restoring from the cloud, so a device with an empty
local repository would push an empty list and wipe the server.

## Fix

- `lib/main.dart` (`a515fe0`): if the user is already signed in (or has
  a persisted email), call `ServerAlertService.restoreUserAlertsFromCloud`
  **before** the first `syncAllRulesToServer`.
- `syncAllRulesToServer` is skipped entirely when `repo.allRules` is empty
  (FIX-EMPTY-SYNC guard).
- `SYNC-4` (later): for guests (`user_default`), also restore from the
  cloud on startup under the `user_default` bucket.

## Prevention

- Baseline marker (`SYNC-2`, `FIX-BASELINE-1`): baseline is written only
  after a non-empty sync or a successful restore, never after an empty
  merge sync.
- `release_gate.md` includes a check that a fresh install restores
  alerts before the first sync.

## References

- Fix commit: `a515fe0` (FIX-EMPTY-SYNC)
- Baseline fix: `0f8bf48` (FIX-BASELINE-1)
- Guest restore: `a126b16` (SYNC-4)
- Related: `SYNC-1a`, `SYNC-1b`, `SYNC-2`, `SYNC-3`
