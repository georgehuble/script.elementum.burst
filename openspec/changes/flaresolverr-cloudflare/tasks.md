## 1. FlareSolverr client module and challenge detection

- [x] 1.1 Create `burst/flaresolverr.py` with a `solve(endpoint, url, method, post_data, headers, max_timeout)` helper that POSTs to the service `/v1` (`request.get`/`request.post`), and verify against the running service that it returns `solution.cookies`, `solution.userAgent`, `solution.status` and `solution.response` for `https://rutracker.org/forum/login.php`
- [x] 1.2 Add a shared challenge detector `is_challenge(status, content)` matching HTTP 403/503 plus indicators ("Just a moment", `cf-challenge`, `challenge-platform`, `__cf_chl`), and verify it flags the raw `requests` login.php response (403) and does not flag the index.php response (200)
- [x] 1.3 Add an `apply_solution(client, solution)` helper that sets the client and global User-Agent to `solution.userAgent` and merges `solution.cookies` into the client cookie jar (persisted via `save_cookies()`), and verify a replayed `requests` GET of `login.php` returns 200

## 2. Challenge-aware retry in the provider HTTP client

- [x] 2.1 Wire challenge detection + solve + retry into `Client.open()`: when bypass is enabled and the response `is_challenge`, call the solver, `apply_solution`, and retry the same request once, returning the final `content`/`status`; verify with a direct call that a challenged login.php request returns 200 after the solve
- [x] 2.2 Ensure solver failures are caught and logged without raising, leaving the original (challenge) response intact; verify by pointing the endpoint at a closed port and confirming the request behaves as before (no crash, no retry loop)
- [x] 2.3 Guard the whole bypass behind the `flaresolverr_enabled` setting so it never runs when disabled; verify a disabled run issues zero `/v1` calls (checked via service logs)

## 3. Pre-solve for protected providers

- [x] 3.1 Add `cf_protected: true` to the `rutracker` entry in `burst/providers/providers.json` and load it through the definitions pipeline (`burst/providers/definitions.py`), verifying the flag is present on `definitions['rutracker']`
- [ ] 3.2 In `burst/provider.py process()`, when a private provider is `cf_protected` and bypass is enabled, pre-solve the provider login page (warm cookies + UA) before the token/CSRF/login steps; verify `login.php` POST with correct test credentials no longer returns a Cloudflare challenge

## 4. Settings and translation strings

- [ ] 4.1 Add global settings `flaresolverr_enabled` (bool, default false) and `flaresolverr_url` (text, default `http://localhost:8191`) to `resources/settings.xml` in an appropriate category, and verify they appear in the Kodi addon settings UI
- [x] 4.2 Add the new string IDs to `resources/language/messages.pot` and merge into locale files, then verify `./scripts/xgettext.sh` passes and `make locales` completes without errors

## 5. Documentation

- [x] 5.1 Document in `README.md` (or `BUILD.md`) the required deployment: `docker run -d --name flaresolverr -p 8191:8191 --restart unless-stopped ghcr.io/flaresolverr/flaresolverr:latest`, the two settings, and how rutracker is affected

## 6. Verification

- [x] 6.1 Run `make check` (flake8) and confirm no new lint errors from the added modules and edits
- [ ] 6.2 End-to-end check with a real rutracker account: burst login succeeds, `bb_session` persists, a search returns results, and selecting a result downloads the `.torrent` via elementum (confirm the `dl.php` fetch is not Cloudflare-blocked)
- [ ] 6.3 Regression check: with bypass disabled and FlareSolverr stopped, other providers (e.g. a public one and another private one) search exactly as before the change
