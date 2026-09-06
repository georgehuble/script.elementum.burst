## Purpose

Lets burst providers pass Cloudflare managed/JS challenges (HTTP 403 "Just a moment...") on
protected endpoints such as the rutracker.org login by delegating the solve to a configured local
FlareSolverr service and reusing the resulting cookies and User-Agent.

## ADDED Requirements

### Requirement: Detect Cloudflare challenge responses

The provider HTTP client SHALL recognise when a provider response is a Cloudflare challenge
(HTTP 403 or 503 whose content carries challenge indicators such as "Just a moment", "cf-challenge",
"challenge-platform", or "__cf_chl") rather than real provider content, and SHALL NOT treat such a
response as a successful provider response.

#### Scenario: Challenge on a protected endpoint

- **WHEN** a provider endpoint returns HTTP 403/503 whose content indicates a Cloudflare challenge
- **THEN** burst records the request as challenged and does not present the response as provider content

### Requirement: Solve challenge and retry through the configured service

When a challenge is detected and the bypass is enabled, burst SHALL delegate the solve to the
configured Cloudflare-solving service, adopt the returned browser User-Agent and cookies for the
provider host, and retry the request so the actual provider response is obtained.

#### Scenario: Successful bypass and retry

- **WHEN** a challenge is detected, bypass is enabled, and the service returns a solution
- **THEN** burst retries the request with the solved cookies and User-Agent and returns the provider content

#### Scenario: Reuse cleared session for later requests

- **WHEN** a challenge for a provider host was solved successfully
- **THEN** subsequent requests to that host are made with the solved cookies and matching User-Agent

### Requirement: Pre-solve protected providers before authentication

A provider marked as Cloudflare-protected SHALL have its clearance established before its
authentication flow starts, so the login request is made with valid clearance rather than failing on
a challenge first.

#### Scenario: Pre-solve before private provider login

- **WHEN** a search runs for a provider marked as Cloudflare-protected and bypass is enabled
- **THEN** burst obtains clearance cookies for that provider host before performing the provider login

### Requirement: Opt-in configuration

Cloudflare bypass SHALL be disabled by default and SHALL only interact with a Cloudflare-solving
service when explicitly enabled and a service endpoint is configured.

#### Scenario: Disabled by default

- **WHEN** the bypass is disabled or no service endpoint is configured
- **THEN** provider requests are made without any interaction with a Cloudflare-solving service

### Requirement: Graceful degradation when the service is unavailable

If the configured Cloudflare-solving service is unreachable, times out, or reports that it cannot
solve a challenge, burst SHALL log the failure and fail the affected request exactly as it would
without the bypass, and SHALL NOT abort the rest of the provider search.

#### Scenario: Service unreachable

- **WHEN** a challenge is detected, bypass is enabled, but the service is unreachable or fails to solve
- **THEN** burst logs the failure and continues the search as if the bypass were disabled
