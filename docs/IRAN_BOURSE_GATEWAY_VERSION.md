# Iranian Bourse gateway - version and host record

| Item | Value |
|---|---|
| Gateway | tsetmc-gateway v0.2.2 (stdlib only, own repository, never inside AlertG) |
| Zip sha256 | `f0c34a71dd1b0e04461e0d3358bf05ae3f681030d52d34d67bffb59b2f21b963` (tsetmc-gateway-v0.2.2.zip) |
| AlertG setting | `IRAN_BOURSE_ALLOWED_VERSIONS` (default `["0.2.2"]`) |

## Reachability tests (max 6 requests per host, never in a loop)

| Date | Host | Result |
|---|---|---|
| 2026-11-13 | server360 (AlertG server, outside Iran) | `selfcheck` FAILED at the first request (Init): `URLError: <urlopen error timed out>`. TSETMC is not reachable from this server. |
| 2026-11-13 | PC with an Iranian IP (Windows, no VPN) | `selfcheck` OK: 3782 instruments, 0 bad rows, quotes for وبملت and فولاد parsed. |

## Host decision (D3)

Pilot: the gateway runs on the Iranian-IP PC, port **8099** (8080 is used by another program on that PC),
with `TSETMC_API_KEY` set, and server360 reaches it through an outbound SSH reverse tunnel
(`http://127.0.0.1:8099` on server360). Later move to an Iranian VPS; only `IRAN_BOURSE_GATEWAY_URL` changes.
The PC must not use a VPN for this process, must not sleep, and exactly one gateway instance may run.

## Findings from the real captures (2026-11-14, tests/fixtures/iran_bourse/real/)

- 3,248 instruments; all pass `validate_quote`; ids are strings; prices are Rial; 0 prices <= 0.
- **Instrument ids are 14-17 digits** (14: 3, 15: 50, 16: 376, 17: 2,819), not 15-18 as the plan assumed.
  AlertG now accepts 12-20 digit ids (`MIN_ID_LEN` / `MAX_ID_LEN` in price.py).
- `market`, `board`, `type`, `sector`, `queue`, `nav`, `eps`, `best_bid`, `best_ask` are often `null`: AlertG tolerates them.
- `/v1/changes?since=<seq>` returned the WHOLE market (about 2.5 MB) right after the gateway re-ran Init
  (`stats.init_ok` 1 -> 2, every `rev` became the new seq). That is the documented "older than the last full reload" case.
  A normal small delta has not been captured yet: capture one during trading hours (Sat-Wed 08:30-19:00 Tehran).
- The PC's Windows clock is not Tehran time. The gateway reported `active_window: false` while the PC showed 10:36 AM
  (it was about 22:05 in Tehran). Do not judge market hours from that PC's clock.
