# Iranian Bourse gateway - version and host record

| Item | Value |
|---|---|
| Gateway | tsetmc-gateway v0.2.2 (stdlib only, own repository, never inside AlertG) |
| Zip sha256 | `f0c34a71dd1b0e04461e0d3358bf05ae3f681030d52d34d67bffb59b2f21b963` (tsetmc-gateway-v0.2.2.zip) |
| AlertG setting | `IRAN_BOURSE_ALLOWED_VERSIONS` (default `["0.2.2"]`) |

## Reachability tests (max 6 requests per host, never in a loop)

| Date | Host | Result |
|---|---|---|
| 2026-11-13 | server360 (AlertG server, outside Iran) | `selfcheck` FAILED at the first request (Init): `URLError: <urlopen error timed out>`. TSETMC is not reachable directly from this server. |
| 2026-11-13 | PC with an Iranian IP (Windows, no VPN) | `selfcheck` OK: 3782 instruments, 0 bad rows, quotes for وبملت and فولاد parsed. |
| 2026-11-20 | server360 via Iranian HTTPS bridge (`aegkala.com/tse-forward.php` v1.1) | `selfcheck` & live cutover OK: gateway runs locally on `server360:8099`, forwarding upstream TSETMC calls through the authenticated, IP-restricted Iranian bridge. |

## Host decision (D3)

### Current production host (updated 2026-11-20, verified 2026-11-25)

- **Autonomous hosting on `server360`**: `tsetmc-gateway v0.2.2` now runs directly on `server360` (`http://127.0.0.1:8099`), managed by `~/tsetmc-gateway/run_gateway.sh` with 2 cron entries (`@reboot` + `*/5` watchdog).
- **Upstream Iranian reachability**: Upstream TSETMC calls go through the authenticated HTTPS bridge on an Iranian host (`aegkala.com/tse-forward.php` v1.1, token-authenticated + restricted to `server360`'s outbound IP). No developer PC or reverse SSH tunnel is required.
- **Stability verification (2026-11-25)**: After **4 days, 15 hours, 55 minutes** of continuous uptime (`pid 3409527`):
  - `poller.requests_made`: `81,282`, **`poller.failures`: `0`**, `poller.resets`: `0`, `stale`: `false`
  - `gateway.instruments`: `3,749`, `bad_rows`: `0`, `init_ok`: `1,563`, `plus_ok`: `32,288`
  - `blocked|timed out` in `gateway.log`: `8` total across 4.5+ days
  - Process RSS memory: `53,696 KB` (`52.4 MB`, well under the `200 MB` budget)
  - Live trading-hours alert end-to-end test (`عیار` / Ayar, IB-17): passed with **1 phone push + 1 Telegram card** (no duplicate delivery).
- **Rollback**: Stop the local gateway (`~/tsetmc-gateway/run_gateway.sh stop`), bring back the Iranian-IP PC + SSH reverse tunnel on `server360:8099` (see `IRAN_BOURSE_RUNBOOK.md` Appendix A). `IRAN_BOURSE_GATEWAY_URL` (`http://127.0.0.1:8099`) remains identical.

### Historical pilot host (2026-11-13 – 2026-11-20, superseded)

Pilot ran the gateway on an Iranian-IP Windows PC (port **8099**, VPN disabled, no sleep, single instance) connected to `server360` through an outbound SSH reverse tunnel (`http://127.0.0.1:8099`). Retired once the `server360` + `aegkala` bridge passed soak verification.

## Findings from the real captures (2026-11-14, tests/fixtures/iran_bourse/real/)

- 3,248 instruments; all pass `validate_quote`; ids are strings; prices are Rial; 0 prices <= 0.
- **Instrument ids are 14-17 digits** (14: 3, 15: 50, 16: 376, 17: 2,819), not 15-18 as the plan assumed.
  AlertG now accepts 12-20 digit ids (`MIN_ID_LEN` / `MAX_ID_LEN` in price.py).
- `market`, `board`, `type`, `sector`, `queue`, `nav`, `eps`, `best_bid`, `best_ask` are often `null`: AlertG tolerates them.
- `/v1/changes?since=<seq>` returned the WHOLE market (about 2.5 MB) right after the gateway re-ran Init
  (`stats.init_ok` 1 -> 2, every `rev` became the new seq). That is the documented "older than the last full reload" case.
- The PC's Windows clock is not Tehran time. The gateway reported `active_window: false` while the PC showed 10:36 AM
  (it was about 22:05 in Tehran). Do not judge market hours from that PC's clock.
