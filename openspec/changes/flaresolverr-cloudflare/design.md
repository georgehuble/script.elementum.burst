## Context

See `proposal.md` — Why for motivation. Current state relevant to the approach:

- Burst talks to providers through a single `requests`-based client [`Client`](../../../burst/client.py)
  whose [`open()`](../../../burst/client.py:315) does GET/POST, keeps cookies in an `LWPCookieJar`
  persisted to `special://temp/burst/common_cookies.jar`, and exposes `content`/`status`/
  `request_cookies`/`response_cookies`. Proxies, Antizapret and custom DNS are configured on the
  session at construction time.
- Private providers (e.g. `rutracker` in [`providers.json`](../../../burst/providers/providers.json:2387))
  authenticate in [`provider.py process()`](../../../burst/provider.py:78): optional token/CSRF
  pre-request, then `client.login()` POSTs `login_object` to `login_path`, and cookies are saved via
  `save_cookies()`. Search then reuses the jar.
- Cloudflare on rutracker.org protects `/forum/login.php` with a JS/managed challenge (HTTP 403
  "Just a moment..."). Public pages (index, and search once logged in) are not challenged. Plain
  Python `requests` cannot run the challenge JS.
- Experiment on this machine: FlareSolverr (real Chromium) solves the challenge; replaying the
  returned `cf_clearance` cookie with the same User-Agent and same IP through plain `requests`
  yields HTTP 200 for login, login POST and search.
- `.torrent` downloads are performed by **elementum**, not burst: burst returns the torrent URI
  with `Cookie` + `User-Agent` appended as headers ([`burst.py`](../../../burst/burst.py:402)).
  Harnessed cookies therefore also travel with the `.torrent` request, keeping the same IP.
- `cf_clearance` is bound to the User-Agent and IP that solved the challenge.

## Goals / Non-Goals

**Goals:**
- Let burst pass Cloudflare managed/JS challenges on protected provider endpoints by delegating the
  solve to a local FlareSolverr HTTP service, then continuing with the existing `requests` client.
- Minimal, opt-in footprint: off by default, no change to providers that do not need it, no browser
  or extra Python packages inside Kodi.
- Reuse existing cookie jar and User-Agent injection so the rest of burst (login persistence,
  search, `.torrent` header appending for elementum) keeps working unchanged.
- Degrade gracefully when FlareSolverr is unreachable: burst behaves exactly as today.

**Non-Goals:**
- Not a transparent proxy for all provider traffic (no per-request browser round-trips).
- Not a generic captcha/Turnstile solver for interactive challenges on arbitrary sites; target is
  the automatable "Just a moment..." class solved by FlareSolverr.
- Not embedding or packaging FlareSolverr/Chromium into the Kodi addon; it runs as an external
  service on the host.

## Decisions

**D1. Harvest-and-replay instead of full proxy.**
Use FlareSolverr only to solve a challenge and harvest `cf_clearance`/session cookies plus the
browser User-Agent, then inject them into the existing `requests` client and retry. This matches the
validated experiment and, unlike a full proxy, also covers elementum's `.torrent` fetch (cookies +
UA already ride on the URI headers).
- Alternative considered: route login/search through FlareSolverr `request.get/post` sessions.
  Rejected as the primary path: each request spins a browser (slow), and elementum's `.torrent`
  download cannot go through FlareSolverr at all. Kept as a documented fallback if a future provider
  requires per-request solving.

**D2. Two trigger points for the bypass.**
1. **Pre-solve** for providers flagged `cf_protected: true` (initially `rutracker`): before the
   login/token steps in `process()`, warm the client by asking FlareSolverr to open the login page,
   then inject cookies + UA. This makes the first login POST pass instead of failing.
2. **Runtime detection retry** in [`Client.open()`](../../../burst/client.py:315): when a response
   looks like a Cloudflare challenge (status 403/503 and content markers such as "Just a moment",
   `cf-challenge`, `challenge-platform`, `__cf_chl`), and the bypass is enabled, solve once, inject,
   retry the same request once. Covers challenge expiry mid-search and providers without the flag.

**D3. New module `burst/flaresolverr.py` (FlareSolverr HTTP client).**
Small pure-HTTP client over the FlareSolverr `/v1` API using the already-vendored `requests`:
- `health(endpoint)` and `solve(endpoint, url, method, post_data, headers, max_timeout)` returning
  the parsed solution (`cookies`, `user_agent`, `status`, `response`).
- `is_challenge(status, content)` shared challenge detector.
- `apply_solution(client, solution)`: set the User-Agent (client + global via `change_agent`) and
  merge returned cookies into the client cookie jar/session, then `save_cookies()`.
Solve failures are caught and logged; they never raise out to the caller.

**D4. Settings (global) + provider flag.**
- Two new settings in [`resources/settings.xml`](../../../resources/settings.xml):
  `flaresolverr_enabled` (bool, default off) and `flaresolverr_url` (text, default
  `http://localhost:8191`), plus the matching `strings.po` entries.
- One new metadata field in `providers.json`: `cf_protected: true` on `rutracker`.
- Read settings once at import time in the same style as existing client settings
  ([`client.py`](../../../burst/client.py:72)).

**D5. User-Agent consistency.**
Because `cf_clearance` is bound to the solving UA, after a solve burst adopts the FlareSolverr UA
(both `Client.user_agent` and the module-global `USER_AGENT` via
[`change_agent()`](../../../burst/client.py:468), since torrent header building reads the global).
Risk of changing the shared global UA mid-batch for concurrently running providers is accepted (UA
stays a modern Chrome UA) and noted in Risks.

**D6. Non-fatal failure semantics.**
If FlareSolverr is unreachable, times out, or reports an unsolvable challenge, burst logs and
continues without the bypass (identical behaviour to today). The feature can only improve, never
regress, the rutracker case.

## Risks / Trade-offs

- [R1] `cf_clearance` expires (rutracker may re-challenge periodically) → D2 runtime detection
  retry re-solves automatically; on expiry burst may return no results for one cycle then recover.
- [R2] Cookie bound to UA + IP; changing VPN/proxy invalidates it → re-solve on next challenge;
  detection retry covers it.
- [R3] elementum's `.torrent` fetch could still be blocked if its HTTP stack/IP diverges from the
  solving context → same host/IP in this deployment; verify with a real account during
  implementation; if blocked, document manual cookie option as fallback.
- [R4] FlareSolverr Docker container not running while the toggle is on → D6 keeps burst functional;
  README documents the one-line `docker run` with `--restart unless-stopped`.
- [R5] Shared global UA changed by a solve could affect other providers running concurrently →
  UA remains a modern Chrome UA; per-client `user_agent` set first; global update only when needed
  for torrent headers.
- [R6] Account lockout risk from repeated failed logins during re-solves → persist `bb_session`
  (already saved by burst) and only solve when a challenge is actually present; never auto-retry
  login storms.

## Migration Plan

- Deployment is additive and off by default: ship the two settings (disabled) and the `rutracker`
  flag; no behavioural change for other providers.
- Host setup (documented in README): `docker run -d --name flaresolverr -p 8191:8191
  --restart unless-stopped ghcr.io/flaresolverr/flaresolverr:latest` (already provisioned during
  exploration on this machine).
- Rollback: disable `flaresolverr_enabled` (or remove the `rutracker` flag) — no code paths removed,
  no data migration.

## Open Questions

- Exact real-account verification (correct credentials → `bb_session` persists; search results;
  `.torrent` download through elementum) must run during implementation; it cannot be validated
  without the user's account.
- Whether rutracker challenges the `.torrent` `dl.php` path even when cookies are present; resolved
  empirically at apply time (R3).
- Optimal `maxTimeout` value for rutracker solves; tune during implementation.
