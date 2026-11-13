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
| - | Iranian host | not tested yet |

## Host decision (D3)

Pending: server360 cannot reach TSETMC, so the gateway must run on a host that can
(an Iranian server), exposed to AlertG over HTTPS with the API key, allowing only server360's IP.
