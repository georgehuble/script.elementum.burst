## Why

The Kodi addon `script.elementum.burst` cannot log into `rutracker.org`: Cloudflare protects
`/forum/login.php` with a JavaScript/managed challenge ("Just a moment...", HTTP 403) that burst's
plain `requests` client cannot pass. On this machine we validated that a real Chromium driven by a
local FlareSolverr service solves the challenge and returns a `cf_clearance` cookie which, replayed
by burst's existing `requests` client with the matching User-Agent and same IP, unlocks login POST,
search and the torrent download path. Burst therefore needs an optional Cloudflare bypass backed by a
FlareSolverr HTTP service.

## What Changes

- Add an optional **Cloudflare bypass** driven by a FlareSolverr service (Docker on the same host,
  `localhost:8191`). Burst never embeds or runs a browser; it only consumes the FlareSolverr HTTP
  `/v1` API.
- Detect a Cloudflare challenge in provider responses (HTTP 403/503 plus "Just a moment..." /
  challenge markers). When detected, ask FlareSolverr to solve the URL, harvest the returned cookies
  (`cf_clearance` and others) plus the browser User-Agent, inject them into the existing
  `requests`-based client (cookie jar + `change_agent`), and retry the original request.
- Add new user settings: bypass enabled/disabled and FlareSolverr endpoint URL.
- Mark Cloudflare-protected providers (initially `rutracker`) with a per-provider flag so burst
  performs a pre-solve before login/search instead of failing mid-flow.
- Add a small FlareSolverr HTTP API client module and wire it into the request path.
- The torrent download benefits automatically: burst already appends `Cookie` + `User-Agent`
  headers to torrent URIs handed to elementum, so the harvested `cf_clearance` travels with the
  `.torrent` request too.
- Documentation for the required FlareSolverr deployment (Docker container with auto-restart).

No breaking changes: the bypass is off by default and only triggers for providers flagged or when a
challenge is detected.

## Capabilities

### New Capabilities
- `cloudflare-bypass`: optional FlareSolverr-backed bypass of Cloudflare "Just a moment..." /
  managed challenges for HTTP providers, covering challenge detection, cookie + User-Agent
  harvesting, and injection into the provider HTTP client.

### Modified Capabilities
<!-- None: openspec/specs is empty; this introduces the first capability. -->

## Impact

- Code: [`burst/client.py`](../../../burst/client.py) (challenge detection, retry, cookie/UA
  injection), new module `burst/flaresolverr.py` (FlareSolverr `/v1` HTTP client),
  [`burst/provider.py`](../../../burst/provider.py) (pre-solve for flagged private providers),
  [`burst/burst.py`](../../../burst/burst.py) (entry wiring).
- Provider metadata: [`burst/providers/providers.json`](../../../burst/providers/providers.json)
  (`rutracker` gains a Cloudflare-protected flag).
- Settings/UI: [`resources/settings.xml`](../../../resources/settings.xml) (new toggle + endpoint)
  and translation strings.
- Dependency/ops: requires the FlareSolverr Docker image (`ghcr.io/flaresolverr/flaresolverr`)
  running on the Kodi host (port `8191`); no Kodi-side Python packages and no browser inside Kodi.
