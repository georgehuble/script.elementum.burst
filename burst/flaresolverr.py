# -*- coding: utf-8 -*-

"""
FlareSolverr Cloudflare bypass client.

Burst never embeds or runs a browser. It only consumes the FlareSolverr HTTP
``/v1`` API (Docker image ``ghcr.io/flaresolverr/flaresolverr``) to solve the
Cloudflare "Just a moment..." / managed challenge on protected endpoints and
reuses the harvested cookies plus browser User-Agent with the plain
``requests``-based client, so that subsequent requests (login POST, search and
the elementum ``.torrent`` fetch) carry a valid ``cf_clearance``.
"""

from future.utils import PY3

import requests
from elementum.provider import log, get_setting
from .client import change_agent

if PY3:
    from urllib.parse import urlencode
    unicode = str
else:
    from urllib import urlencode
    unicode = unicode

# Kodi settings (read once at import time, same style as in burst/client.py)
flaresolverr_enabled = get_setting("flaresolverr_enabled", bool)
flaresolverr_url = get_setting("flaresolverr_url", unicode)
if not flaresolverr_url:
    flaresolverr_url = "http://localhost:8191"
flaresolverr_url = flaresolverr_url.strip().rstrip("/")

# Default FlareSolverr service location
DEFAULT_ENDPOINT = "http://localhost:8191"

# Time in milliseconds FlareSolverr is allowed to spend solving a challenge.
DEFAULT_MAX_TIMEOUT = 60000

# Cloudflare challenge markers
CHALLENGE_INDICATORS = [
    "just a moment",
    "cf-challenge",
    "challenge-platform",
    "__cf_chl",
]
CHALLENGE_STATUSES = (403, 503)


def is_challenge(status, content):
    """ Shared challenge detector.

    Returns ``True`` when a provider response looks like a Cloudflare challenge
    rather than real provider content: an HTTP 403/503 whose content carries a
    known challenge indicator such as "Just a moment...", ``cf-challenge``,
    ``challenge-platform`` or ``__cf_chl``.
    """
    if status not in CHALLENGE_STATUSES:
        return False
    if not content:
        return False

    lowered = content.lower()
    for indicator in CHALLENGE_INDICATORS:
        if indicator in lowered:
            return True
    return False


def solve(endpoint, url, method="GET", post_data=None, headers=None, max_timeout=DEFAULT_MAX_TIMEOUT):
    """ Ask the FlareSolverr service to solve ``url``.

    Args:
        endpoint    (str): Base URL of the FlareSolverr service (without ``/v1``)
        url         (str): URL to solve
        method      (str): HTTP method to use, ``GET`` or ``POST``
        post_data  (dict): POST payload for ``request.post``
        headers    (dict): Extra headers to send with the solve request
        max_timeout  (int): Time in milliseconds FlareSolverr may spend solving

    Returns:
        dict: The parsed ``solution`` (with ``cookies``, ``userAgent``,
        ``status`` and ``response``) on success, or ``None`` on any failure.

    Failures are logged and swallowed, they never raise out to the caller.
    """
    try:
        api_url = "%s/v1" % (endpoint or flaresolverr_url or DEFAULT_ENDPOINT)
        command = "request.post" if method and method.upper() == "POST" else "request.get"

        payload = {
            "cmd": command,
            "url": url,
            "maxTimeout": max_timeout,
        }
        if command == "request.post" and post_data:
            if isinstance(post_data, dict):
                payload["postData"] = urlencode(post_data)
            else:
                payload["postData"] = post_data
        if headers:
            payload["headers"] = headers

        log.debug("FlareSolverr %s request for %s to %s" % (command, repr(url), repr(api_url)))
        response = requests.post(api_url, json=payload, timeout=(max_timeout / 1000.0) + 10)
        data = response.json()

        if data.get("status") != "ok":
            log.error("FlareSolverr could not solve %s: %s" % (repr(url), data.get("message", repr(data))))
            return None

        solution = data.get("solution")
        if not solution:
            log.error("FlareSolverr returned no solution for %s" % repr(url))
            return None

        log.debug("FlareSolverr solved %s with status %s" % (repr(url), solution.get("status")))
        return solution
    except Exception as e:
        import traceback
        log.error("FlareSolverr solve error for %s: %s" % (repr(url), repr(e)))
        map(log.debug, traceback.format_exc().split("\n"))
        return None


def _merge_cookie(client, cookie):
    """ Translate a FlareSolverr cookie and merge it into the client jar. """
    name = cookie.get("name")
    domain = cookie.get("domain")
    value = cookie.get("value")
    if not name or value is None:
        return False

    # Drop any previously stored cookie with the same name on this host so a
    # stale (e.g. expired) value never shadows the freshly solved one.
    host = (domain or "").lstrip(".")
    for existing in list(client._cookies):
        if existing.name == name and existing.domain.lstrip(".") == host:
            try:
                client._cookies.clear(existing.domain, existing.path, existing.name)
            except Exception:
                pass

    expiry = cookie.get("expires") or 0
    expiration_date = None
    try:
        if int(expiry) > 0:
            expiration_date = int(expiry)
    except Exception:
        expiration_date = None

    client.add_cookie({
        "domain": domain or "",
        "name": name,
        "value": value,
        "path": cookie.get("path") or "/",
        "secure": bool(cookie.get("secure")),
        "expirationDate": expiration_date,
        "rest": {"HttpOnly": bool(cookie.get("httpOnly"))},
    })
    return True


def apply_solution(client, solution):
    """ Inject a FlareSolverr solution into a burst client.

    Sets the client (and module-global) User-Agent to the browser User-Agent
    that solved the challenge and merges the returned cookies into the client
    cookie jar, persisted via ``save_cookies()``.

    Returns:
        bool: ``True`` on success, ``False`` if no solution could be applied.

    Failures are logged and swallowed, they never raise out to the caller.
    """
    try:
        if not solution:
            return False

        user_agent = solution.get("userAgent")
        if user_agent:
            client.user_agent = user_agent
            change_agent(user_agent)

        cookies = solution.get("cookies")
        if cookies:
            client._read_cookies()
            added = 0
            for cookie in cookies:
                if _merge_cookie(client, cookie):
                    added += 1
            if added:
                log.debug("FlareSolverr merged %d cookies into the client" % added)
                client.save_cookies()

        return True
    except Exception as e:
        import traceback
        log.error("FlareSolverr failed applying solution: %s" % repr(e))
        map(log.debug, traceback.format_exc().split("\n"))
        return False


def pre_solve(client, url):
    """ Pre-solve a provider URL to warm cookies + User-Agent.

    Used before the authentication flow of Cloudflare-protected providers so
    the login request carries valid clearance instead of failing on a challenge.

    Args:
        client (Client): The burst client to apply the solution to
        url       (str): URL to pre-solve (e.g. the provider login page)

    Returns:
        bool: ``True`` when a solution was applied, ``False`` otherwise.
    """
    if not flaresolverr_enabled or not flaresolverr_url:
        return False
    if not url:
        return False

    log.debug("FlareSolverr pre-solving %s" % repr(url))
    solution = solve(flaresolverr_url, url, method="GET")
    return apply_solution(client, solution)
