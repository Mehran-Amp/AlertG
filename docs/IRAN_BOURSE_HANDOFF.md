# Iranian Bourse - handoff plan for the programmer (phases 18c to 20)

Audience: the programmer (human or AI coding agent). Work through the micro-phases **in order, one at a time**.
Every micro-phase has: a goal, the files it touches, a short **PROMPT**, **acceptance tests** (commands with the expected result) and **if it fails**.
Do not start the next micro-phase until every acceptance test of the current one passes. After the last phase, send the **final report** (bottom) to the project owner.

## 0. Context in one page

The Flutter app talks only to the AlertG server (server360, Germany). The server needs Bourse prices from TSETMC, which
cannot be reached directly from server360 (`old.tsetmc.com` times out; the main site answers 403 without a browser User-Agent).
Measured on 2026-11-19: `aegkala.com` (Iranian host, DirectAdmin + LiteSpeed, PHP 8.1) fetches TSETMC fast
(Init 0.09 s, Plus 1.25 s) and server360 reaches `aegkala.com` fast (connect 0.12 s).

**Before (today, running):** server360 -> `127.0.0.1:8099` -> SSH reverse tunnel -> gateway on the owner's PC (Iranian IP) -> TSETMC.
**After (target of this plan):** server360 -> `127.0.0.1:8099` -> gateway (python, runs ON server360) -> `https://aegkala.com/tse-forward.php/<BRIDGE_TOKEN>` -> TSETMC.
No PC and no tunnel in the chain. `IRAN_BOURSE_GATEWAY_URL` and the gateway key in the AlertG `.env` do not change.

Already done and merged/open: the bridge `scripts/aegkala/tse-forward.php` (PR #23; live and verified: HTTP 200, 1.36 MB in 2.5 s through the real URL),
the runbook `docs/IRAN_BOURSE_RUNBOOK.md`, the PC supervisor script (PR #21, becomes obsolete after phase 18d).

Facts you need:
- Gateway source: `C:\tsetmc-gateway\tsetmc_gateway\` on the owner's PC (python >= 3.10, **no dependencies**). Run as `python -m tsetmc_gateway`.
  Config only through environment: `TSETMC_HOST`, `TSETMC_PORT` (default 8080), `TSETMC_API_KEY`, `TSETMC_BASE_URL`, `TSETMC_HTTP_TIMEOUT` (default 20), `TSETMC_POLL_INTERVAL` (5), `TSETMC_IDLE_INTERVAL` (60).
  It requests `<BASE_URL>/MarketWatchInit.aspx?h=0&r=0` and `<BASE_URL>/MarketWatchPlus.aspx?h=<n>&r=<n>`.
- server360: user `aisocial`, SSH port **8443**, host `aisocialfeed.com`; Python 3.11.11 (pyenv shim `~/.pyenv/shims/python3`); AlertG in `~/AlertG1/AlertG`
  on branch `feat/server-price-gateway` (update with `git pull origin main` then `./run_server.sh restart`; **never `git checkout main` there**).
- Gateway endpoints (header `X-API-Key`): `/health`, `/v1/market`, `/v1/symbols?q=...`, `/v1/changes?since=0`.
- Server endpoints: `/api/iran-bourse/status?probe=true` (header `X-Admin-Key`), `/api/iran-bourse/board`.
- The bridge IP allow-list contains server360's public IP `5.9.73.60`; the bridge token lives only in `public_html/tse-forward.config.php` on aegkala.

## Rules (read first)

1. **Isolation:** never change code of other markets (crypto, stocks, Iranian exchanges). Only Bourse files, scripts and docs.
2. **Secrets:** never print, commit or paste keys/tokens/passwords. In every command shown to the owner use placeholders:
   `000000` = API_KEY, `111111` = ADMIN_KEY, `222222` = gateway key, `333333` = TSETMC_API_KEY (same secret as 222222), `444444` = bridge token.
   On the server read keys from files, e.g. `K=$(grep '^IRAN_BOURSE_GATEWAY_KEY=' ~/AlertG1/AlertG/.env | cut -d= -f2-)`.
3. **Label every command** with where it runs: **(server360)**, **(PC)** or **(aegkala)**.
4. **One concern per step.** Stop at the first failing acceptance test and report it; do not improvise around it.
5. Python changes need tests (pytest); the full suite must equal the baseline: 921 passed and 4 known failures (the other developer's `test_phase4_*`, `test_phase5_*`, `test_phase7_*`).
6. Commit trailers: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01ERrcorqWhpefRndpxyTR3w`. One PR per phase, never merge without the owner saying "merge".
7. Bourse gateway = black box: do not change its source. Anything it needs is configured through environment variables.

---

## Phase 18c - run the gateway on server360 (side by side, on port 8098)

### 18c-1 Copy the gateway code to the server
- Goal: `~/tsetmc-gateway/tsetmc_gateway/` exists on server360.
- Touches: nothing in the repo.
- PROMPT: "Create `~/tsetmc-gateway` on server360 and copy the folder `C:\tsetmc-gateway\tsetmc_gateway` into it with scp, using key `%USERPROFILE%\.ssh\bourse_tunnel` and port 8443. Do not copy `.env`, `api_key.txt`, `fixtures_real*` or `.github`."
- Commands: **(server360)** `mkdir -p ~/tsetmc-gateway`; **(PC)** `scp -P 8443 -i "$env:USERPROFILE\.ssh\bourse_tunnel" -r C:\tsetmc-gateway\tsetmc_gateway aisocial@aisocialfeed.com:~/tsetmc-gateway/`
- Acceptance: **(server360)** `cd ~/tsetmc-gateway && ~/.pyenv/shims/python3 -c "import tsetmc_gateway; print('import ok')"` prints `import ok`;
  `ls ~/tsetmc-gateway/tsetmc_gateway | head` shows `__main__.py`, `config.py`, `client.py`; `find ~/tsetmc-gateway -name "*.env*" -o -name "api_key*"` prints nothing.
- If it fails: `Permission denied` -> key not installed on the server (it was installed on 2026-11-18, test `ssh -p 8443 -i <key> -o BatchMode=yes aisocial@aisocialfeed.com echo ok`).

### 18c-2 Create the gateway environment file
- Goal: `~/tsetmc-gateway/gateway.env`, mode 600, owner `aisocial`, containing the five variables, **without printing any secret**.
- PROMPT: "Create `gateway.env` on server360 with `TSETMC_HOST=127.0.0.1`, `TSETMC_PORT=8098`, `TSETMC_HTTP_TIMEOUT=30`, `TSETMC_API_KEY` copied from `IRAN_BOURSE_GATEWAY_KEY` in `~/AlertG1/AlertG/.env`, and `TSETMC_BASE_URL=https://aegkala.com/tse-forward.php/<BRIDGE_TOKEN>` where the token is typed by the owner at a hidden prompt (`read -rs`). Never echo values."
- Acceptance: **(server360)**
  - `stat -c '%a %U' ~/tsetmc-gateway/gateway.env` -> `600 aisocial`
  - `cut -d= -f1 ~/tsetmc-gateway/gateway.env | sort` -> exactly `TSETMC_API_KEY, TSETMC_BASE_URL, TSETMC_HOST, TSETMC_HTTP_TIMEOUT, TSETMC_PORT`
  - `grep -c '^TSETMC_BASE_URL=https://aegkala.com/tse-forward.php/.\{24,\}$' ~/tsetmc-gateway/gateway.env` -> `1`
  - `[ "$(grep '^TSETMC_API_KEY=' ~/tsetmc-gateway/gateway.env | cut -d= -f2-)" = "$(grep '^IRAN_BOURSE_GATEWAY_KEY=' ~/AlertG1/AlertG/.env | cut -d= -f2-)" ] && echo same || echo DIFFERENT` -> `same`
- If it fails: fix the file; never paste its content anywhere.

### 18c-3 `scripts/bourse/run_gateway.sh`
- Goal: a small supervisor script in the repo (new file, plus `tests/test_run_gateway_script.py`).
- Behaviour: `start | stop | restart | status | ensure`. Reads `~/tsetmc-gateway/gateway.env` (override with `GATEWAY_DIR`). Pid file `~/tsetmc-gateway/gateway.pid`, log `~/tsetmc-gateway/gateway.log` (rotate at 5 MB).
  `start` refuses if already running or if the port is busy; `ensure` = start only if not running (idempotent, quiet when running; for cron). Uses an absolute python path (`PYTHON` env, default `$HOME/.pyenv/versions/3.11.11/bin/python3`, fall back to `python3`), because cron has no pyenv shims.
  Never prints env values; `status` prints pid, port, uptime and `running`/`stopped`, exit code 0/3.
- PROMPT: "Write `scripts/bourse/run_gateway.sh` as described (POSIX sh, `set -eu`), and pytest tests that run it against a fake gateway module in a temp dir (start, double start refused, status, stop, ensure revives a killed process, no secret in the output)."
- Acceptance: `python3 -m pytest tests/test_run_gateway_script.py -q` all pass; `shellcheck scripts/bourse/run_gateway.sh` clean if shellcheck exists; full suite = baseline (921 + new tests passed, 4 known failures).
- Deploy to the server with the normal flow (PR -> owner says merge -> **(server360)** `git pull origin main`; no server restart needed).

### 18c-4 Start on port 8098 and compare with the PC gateway
- Acceptance (all **(server360)**):
  1. `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh start && sleep 20 && ~/AlertG1/AlertG/scripts/bourse/run_gateway.sh status` -> `running`.
  2. `K=$(grep '^TSETMC_API_KEY=' ~/tsetmc-gateway/gateway.env | cut -d= -f2-); curl -s -m 10 -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $K" http://127.0.0.1:8098/health` -> `200` (a `503` in the first 1-2 minutes is "still loading": retry every 20 s up to 3 minutes).
  3. `curl -s -m 10 -H "X-API-Key: $K" http://127.0.0.1:8098/health | python3 -m json.tool` shows about **3700+ instruments** (PC gateway showed 3778-3882) and not stale.
  4. `curl -s -m 20 -H "X-API-Key: $K" "http://127.0.0.1:8098/v1/symbols?q=%D8%B9%DB%8C%D8%A7%D8%B1"` (q = عیار) returns an instrument with id `34144395039913458` (a String).
  5. `curl -s -m 30 -H "X-API-Key: $K" "http://127.0.0.1:8098/v1/changes?since=0" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('quotes') or d.get('rows') or d))"` prints a number >= 3500.
  6. Compare with the PC gateway through the tunnel (still on 8099): the same `/v1/symbols?q=` call returns the same id, and `/health` instrument counts differ by less than 1%.
  7. `tail -20 ~/tsetmc-gateway/gateway.log` has no tracebacks; `grep -c -i "timed out\|error" ~/tsetmc-gateway/gateway.log` is small (< 5) after 5 minutes.
- If it fails: `502` from the bridge (log line `upstream ...`) -> check the bridge (`curl` the bridge URL by hand); `401` in the gateway log -> wrong bridge token in `gateway.env`; `403` -> the bridge IP allow-list does not contain `5.9.73.60`.

### 18c-5 Watchdog cron
- Goal: the gateway comes back by itself and after a reboot.
- PROMPT: "Add two crontab lines for user aisocial (do not touch other lines): `@reboot` and `* * * * *`, both calling `run_gateway.sh ensure`, with output appended to `~/tsetmc-gateway/cron.log`. Show the final `crontab -l`."
- Acceptance: **(server360)** `crontab -l | grep -c run_gateway` -> `2`; `kill $(cat ~/tsetmc-gateway/gateway.pid)`; wait 70 s; `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh status` -> `running` with a **new** pid; `cron.log` has no errors.
- Note: keep this cron pointing at port 8098 until phase 18d moves it.

---

## Phase 18d - cut over to the server-side gateway

The owner must be present for 18d. Do it when the market is closed or quiet (Thursday/Friday, or after 19:00 Tehran = 16:30 server time CET).

### 18d-1 Prepare rollback (nothing changes yet)
- Write down the rollback (in the PR description): (a) **(server360)** `run_gateway.sh stop`, remove the two cron lines; (b) **(PC)** start the old gateway + tunnel with `C:\tsetmc-gateway\start_bourse.ps1`; (c) **(server360)** the `curl .../v1/market` check returns `200`.
- Acceptance: the owner confirms the PC old script still starts (a dry run `-Check` if it exists) **before** step 18d-2.

### 18d-2 Stop the PC chain
- **(PC)** close the gateway and tunnel windows (or Ctrl+C the supervisor). **(PC)** `Get-Process python, ssh -ErrorAction SilentlyContinue` shows none belonging to the gateway/tunnel.
- Acceptance **(server360)**: `(echo > /dev/tcp/127.0.0.1/8099) 2>/dev/null && echo open || echo CLOSED` -> `CLOSED` (the tunnel is gone; port 8099 is free).

### 18d-3 Move the server gateway to 8099
- **(server360)** `sed -i 's/^TSETMC_PORT=.*/TSETMC_PORT=8099/' ~/tsetmc-gateway/gateway.env && ~/AlertG1/AlertG/scripts/bourse/run_gateway.sh restart` and wait for `/health` = 200 on port 8099 (use the same loop as 18c-4 step 2 with port 8099).
- Acceptance (all **(server360)**):
  1. `curl -s -m 10 -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $K" http://127.0.0.1:8099/v1/market` -> `200` (same command the owner used before).
  2. `A=$(grep '^ADMIN_KEY=' ~/AlertG1/AlertG/.env | cut -d= -f2-); curl -s -H "X-Admin-Key: $A" "http://127.0.0.1:8000/api/iran-bourse/status?probe=true" | python3 -m json.tool` shows `enabled: true`, the poller not failing, the gateway probe OK.
  3. `curl -s -H "X-API-Key: <API_KEY from .env>" "http://127.0.0.1:8000/api/iran-bourse/board?limit=3"` returns 3 rows with `price` and `session`.
  4. In the app (owner): Create alert -> Bourse card -> the list opens with rows; open "عیار" and the price appears.
- If it fails: run the rollback of 18d-1 immediately and report.

### 18d-4 Live alert test (also closes the open "duplicate notification" question, IB-17)
- Market must be open (Saturday-Wednesday 08:30-19:00 Tehran). Owner: create a price alert "above" for "عیار" with an amount clearly **below** the current last price.
- Acceptance: within about 3 minutes the owner gets **exactly one** phone notification and **one** Telegram message. The owner reports the two counts ("phone X, Telegram Y"). Then delete the test alert.
  - Phone 1 / Telegram 1 -> IB-17 closed without code.
  - Phone 2 / Telegram 1 -> double notification: open phase IB-17b (the phone skips local checks for `tsetmc` alerts; a one-line guard in `scheduler_service.dart`, owner approval first).
  - Phone 0 -> push token problem (old dead tokens), not a Bourse bug.

### 18d-5 24-hour observation
- Each of the next two market days **(server360)** run the three-command check from `docs/IRAN_BOURSE_RUNBOOK.md` section 1 once in the morning and once in the evening and note the results.
- Acceptance: `poller` failures stay near 0; `grep -c "blocked\|timed out" ~/tsetmc-gateway/gateway.log` does not grow during market hours; `ps -o pid,etime,rss -p $(cat ~/tsetmc-gateway/gateway.pid)` shows memory (rss) staying under about 200 MB.

---

## Phase 18e - documentation and cleanup (after 18d is stable for two market days)

- 18e-1 Update `docs/IRAN_BOURSE_RUNBOOK.md` (Persian): new architecture (section 0), new checks (gateway log, `run_gateway.sh status`, bridge status codes 401/403/404/400/502 and what each means), remove the PC-tunnel steps or move them to an "old setup / emergency fallback" appendix. Acceptance: every command in the runbook is run once by the programmer and works.
- 18e-2 Close PR #21 (PC supervisor) without merging (keep the scripts only if the owner wants a cold standby; otherwise delete the branch). Acceptance: PR closed with a comment.
- 18e-3 Update `docs/IRAN_BOURSE_GATEWAY_VERSION.md`: the hosting decision changed from "PC + tunnel" to "gateway on server360 + aegkala bridge". Acceptance: the file states the date, the reason and the rollback.
- 18e-4 **(aegkala)** delete `tse-probe.php` and `tse-probe.config.php` if they still exist. Acceptance: `curl -s -o /dev/null -w "%{http_code}" https://aegkala.com/tse-probe.php` -> `404`.
- 18e-5 Optional: add a second bridge allow-listed IP or a second bridge host as a spare (only if the owner asks).

## Phase 19 - rotate the secrets (do it when the app is ready for real users)

All of these were exposed in chat during development and must be considered compromised. Rotate in this order, one per step, testing after each:

1. **GitHub classic token.** It is stored in the server's git remote URL. Create a fine-grained token (repo `Mehran-Amp/AlertG`, Contents: read-only, expires in 90 days), **(server360)** `read -rs -p "token: " T; echo; git remote set-url origin "https://x-access-token:${T}@github.com/Mehran-Amp/AlertG.git"; unset T` (typed at the hidden prompt), then delete the old classic token. Acceptance: `git ls-remote origin | head -1` prints a hash; `git pull origin main` works. Check the PC repo too: `git remote -v` must not contain `@` before `github.com`.
2. **Gateway key (`222222`/`333333`).** One new random value (`openssl rand -hex 24`, 48 chars) in two places on server360 only: `IRAN_BOURSE_GATEWAY_KEY` in the AlertG `.env` and `TSETMC_API_KEY` in `~/tsetmc-gateway/gateway.env`. Restart the gateway (`run_gateway.sh restart`) and the server (`./run_server.sh restart`). Acceptance: `/health` with the new key = 200, with the old key = 401; `/api/iran-bourse/status?probe=true` OK. (There is no PC copy any more.)
3. **Bridge token (`444444`).** New value in `public_html/tse-forward.config.php` (**aegkala**) and in `TSETMC_BASE_URL` in `gateway.env` (**server360**); restart the gateway. Acceptance: the bridge URL with the old token -> 401, with the new -> 200; gateway `/health` 200.
4. **API key (`000000`) and admin key (`111111`).** The app sends the API key, so find where the app gets it (settings / build) first; plan a rebuild and reinstall of the app. Acceptance: old key -> 401 on the server, new key works from the rebuilt app.
5. **Server SSH password.** Key login for the owner works (key already installed for the tunnel; add the owner's own key too). Then **(server360)** set `PasswordAuthentication no` in the SSH config, keep a second logged-in session open while reloading sshd, and test a fresh login with the key. Acceptance: `ssh -o PreferredAuthentications=password ...` is refused; key login works. Also remove the old `bourse_tunnel` public key from `~/.ssh/authorized_keys` once the PC tunnel is retired.

## Phase 20 - optional polish (any order, each its own PR, owner chooses)

- Commodities tab for the 13 saffron certificates and grouping of the ~33 untyped rows currently in "other".
- "Alerts on this symbol" badge on list rows (the app already stores alerts locally).
- Top-movers tab (the board endpoint already sorts by `change`).
- Hide the redundant "alerts are checked only when the market is open" line in the alert form when the market is closed.
- Slower local polling in the app for `tsetmc` alerts (only if IB-17b shows it is needed).

---

## Phase 21 - Iranian-market alert types (only after 18d is stable for two market days)

What the code already has (checked 2026-11-20 in `app/markets/iran_bourse/`): the gateway quote contains `best_bid`, `best_ask`, `queue`,
`volume`, `value`, `upper_limit`, `lower_limit`, `yesterday`, `last_change_pct`. `alert_rules.py` (IB-8) **already implements**
`percentChange` and `absolutePriceChange` against **yesterday's close** (`prev_close`), with `price_field` last/close.
Not available from the gateway: any volume history (only today's volume).
Shared-code rule: `app/engine/checker.py` is shared by all markets. Put all Bourse logic in `alert_rules.py`; the hook in `checker.py` must be a
few lines guarded by the Bourse market and needs the owner's explicit approval before it is written.

### 21a Inventory (read-only, no code)
- PROMPT: "On server360 read 10 symbols from `/v1/quote/{id}` (one that is at its upper limit, one at its lower limit if any today, three normal, three funds). Write the real values of `queue`, `best_bid`, `best_ask`, `upper_limit`, `lower_limit`, `volume`, `last` into `docs/IRAN_BOURSE_ALERT_TYPES.md` (new file, a table plus the exact JSON shape of `queue`). No keys or tokens in the file."
- Acceptance: the file exists; it states for a symbol at its upper limit what `best_ask` and `queue` look like (this defines "buy queue"); `git diff --stat` shows only that file.

### 21b Percent change vs yesterday: verify, do not rebuild
- PROMPT: "Check end to end that a `percentChange` alert (e.g. +3% from yesterday) on a Bourse symbol works: unit test with a fake quote in `tests/`, and report whether the Flutter alert form for Bourse exposes it. Do not change the checker."
- Acceptance: test passes; the report says YES/NO for the app form. If NO, 21b-ui becomes a Flutter micro-phase (form option plus strings in `BourseStrings`, widget test) for the owner to approve.

### 21c Buy-queue / sell-queue alert (server, `alert_rules.py`)
- Definition (confirm with 21a data before coding): buy queue = last or best bid equals `upper_limit` and there are no sell offers; sell queue is the mirror at `lower_limit`. Optional minimum queue volume.
- PROMPT: "Add pure helpers `is_buy_queue(meta)` / `is_sell_queue(meta)` and a new condition type `queueBuy` / `queueSell` for Bourse only, edge-triggered (fires when entering the queue, re-arms after leaving), one-shot like other Bourse alerts. Tests with fake quotes: entering, staying, leaving, limits missing, symbol not traded, market closed."
- Acceptance: new tests pass; full suite equals baseline; the other markets' tests are unchanged and green.

### 21d Queue alert in the app (Flutter)
- PROMPT: "Add the two options to the Bourse alert form with Persian strings in `BourseStrings`, keep RTL and theme tokens, widget tests."
- Acceptance: `flutter analyze lib/features/iran_bourse test/<file>` clean; the new widget tests pass.

### 21e Volume alert, absolute first
- PROMPT: "Add `volumeAbove`: fires when today's `volume` crosses a number the user typed. Same structure as 21c."
- Acceptance: tests as 21c.
- Later, optional (21f): "unusual volume" needs history. Store each symbol's daily volume at 19:00 Tehran in a small table, then compare to the 20-day average. This is a larger design, so it gets its own plan and the owner's approval before any code.

Legal note before any public release: the data source is unofficial; check TSETMC / Securities and Exchange Organization terms before showing Bourse data to many users.

---

## Final report (send this to the project owner / Claude)

Copy, fill and send:

```
PHASE REPORT
Phases finished: <18c-1 ... 18d-5, 18e-x, 19, 21x>
PRs: <numbers and merge state>
Acceptance tests that PASSED: <list>
Acceptance tests that FAILED or were skipped: <list + exact output, secrets removed>
Gateway on server360: running? <status output> port <8098/8099> uptime <...>
Bridge check: code=<200> size=<...> time=<...>
Duplicate-notification test: phone <X>, Telegram <Y>
Python suite: <passed>/<failed>  (baseline: 921 passed, 4 known failures)
Anything surprising: <free text>
Next phase proposed: <...>
```
