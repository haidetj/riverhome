"""
Thin client for the Helldivers 2 Training Manual community API.

Docs / source: https://helldiverstrainingmanual.com/api
Everything here is read-only and unauthenticated. The API is polite about a
User-Agent, rate-limits softly, and occasionally 5xx's during a war tick — so
every call retries with backoff and returns (payload, sha256) so callers can
skip downstream work when nothing changed.

Endpoints we lean on (all under https://helldiverstrainingmanual.com/api):
    /v1/planets                 full per-planet state, keyed by planetIndex
    /v1/war/campaign            the ACTIVE set (which planets have a campaign)
    /v1/war/status              global war tick + planetEvents (defense timers)
    /v1/war/major-orders        current Major Order(s)

Field shapes drift between game patches; callers must use .get() and tolerate
missing keys. This module deliberately does no normalisation — it hands back
raw JSON plus a content hash.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request

BASE = "https://helldiverstrainingmanual.com/api"

# A descriptive UA is requested by the maintainers; keep a contact in it.
USER_AGENT = "hd2-kit-advisor/0.2 (+https://github.com/haidetj/hd2-kit) sourcing-canary"

ENDPOINTS = {
    "planets": "/v1/planets",
    "campaign": "/v1/war/campaign",
    "status": "/v1/war/status",
    "major_orders": "/v1/war/major-orders",
}


def _sha256(payload) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def fetch(path: str, *, retries: int = 4, timeout: int = 20, base: str = BASE):
    """GET `base + path`, parse JSON, retry with exponential backoff.

    Returns (payload, sha256). Raises the last error if every attempt fails.
    """
    url = base.rstrip("/") + path
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            payload = json.loads(raw)
            return payload, _sha256(payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last!r}") from last


def fetch_named(name: str, **kw):
    """Fetch one of the well-known ENDPOINTS by short name."""
    if name not in ENDPOINTS:
        raise KeyError(f"unknown endpoint {name!r}; known: {sorted(ENDPOINTS)}")
    return fetch(ENDPOINTS[name], **kw)


def sha256(payload) -> str:
    """Public helper so callers can hash payloads loaded from disk (offline mode)."""
    return _sha256(payload)
