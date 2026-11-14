# -*- coding: utf-8 -*-
"""Async client for the tsetmc-gateway HTTP API.

Rules: reuse the shared httpx client, send X-API-Key, one request in flight,
no hidden retries, typed errors. Only the six calls of the plan are exposed.
"""
import asyncio
import json
import time
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import quote as url_quote

import httpx

from app.markets.iran_bourse.mapping import MappingError, validate_quote

DEFAULT_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
DEFAULT_ALLOWED_VERSIONS = ("0.2.2",)


class BourseError(Exception):
    """Base class for every gateway failure."""


class BourseUnauthorized(BourseError):
    """HTTP 401: wrong or missing X-API-Key."""


class BourseNotReady(BourseError):
    """HTTP 503: the gateway has not loaded market data yet."""


class BourseNotFound(BourseError):
    """HTTP 404: unknown instrument."""


class BourseTimeout(BourseError):
    """The gateway did not answer in time."""


class BourseConnectionError(BourseError):
    """The gateway could not be reached."""


class BourseBadResponse(BourseError):
    """Unexpected status, malformed JSON, or a contract violation."""


class BourseBadVersion(BourseError):
    """The gateway version is not in the allowed list."""


class BourseClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        allowed_versions: Iterable[str] = DEFAULT_ALLOWED_VERSIONS,
        verify_version_every: Optional[float] = None,
        clock=time.monotonic,
    ):
        self._http = http
        self._base = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key, "Accept": "application/json"}
        self._timeout = timeout
        self._allowed = tuple(allowed_versions)
        self._lock = asyncio.Lock()  # one request in flight (rules N12 / Phase 4)
        # Version gate (IB-2c): when set, the first data call and then every N seconds checks /health.version.
        # A bad version is remembered for 60 s so a wrong gateway is not hammered with /health calls.
        self._verify_every = verify_version_every
        self._clock = clock
        self._ver_checked_at: Optional[float] = None
        self._ver_error: Optional[str] = None

    def version_state(self) -> Dict[str, Any]:
        return {"gate": self._verify_every is not None, "ok": self._ver_checked_at is not None and self._ver_error is None,
                "error": self._ver_error, "allowed": list(self._allowed)}

    async def _gate(self) -> None:
        now = self._clock()
        if self._ver_checked_at is not None:
            age = now - self._ver_checked_at
            if self._ver_error is None and age < self._verify_every:
                return
            if self._ver_error is not None and age < 60.0:
                raise BourseBadVersion(self._ver_error)
        try:
            await self.check_version()
            self._ver_error = None
        except BourseBadVersion as exc:
            self._ver_error = str(exc)
            self._ver_checked_at = now
            raise
        self._ver_checked_at = now

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._base + path
        if self._verify_every is not None and path != "/health":
            await self._gate()
        async with self._lock:
            try:
                resp = await self._http.get(
                    url, params=params, headers=self._headers, timeout=self._timeout
                )
            except httpx.TimeoutException as exc:
                raise BourseTimeout(f"gateway timeout on {path}") from exc
            except httpx.TransportError as exc:
                raise BourseConnectionError(f"gateway unreachable: {type(exc).__name__}") from exc

        status = resp.status_code
        if status == 401:
            raise BourseUnauthorized("gateway rejected the API key")
        if status == 503:
            raise BourseNotReady("gateway has not loaded market data yet")
        if status == 404:
            raise BourseNotFound(f"not found: {path}")
        if status != 200:
            raise BourseBadResponse(f"unexpected HTTP {status} on {path}")
        try:
            body = json.loads(resp.content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BourseBadResponse(f"malformed JSON from {path}") from exc
        if not isinstance(body, dict):
            raise BourseBadResponse(f"unexpected body type from {path}")
        return body

    @staticmethod
    def _envelope(body: Dict[str, Any], path: str) -> Tuple[Any, Dict[str, Any]]:
        if "data" not in body or not isinstance(body.get("meta"), dict):
            raise BourseBadResponse(f"missing meta/data in {path}")
        return body["data"], body["meta"]

    # ---- the six calls used by AlertG ------------------------------------
    async def health(self) -> Dict[str, Any]:
        body = await self._get("/health")
        if "version" not in body:
            raise BourseBadResponse("health has no version")
        return body

    async def check_version(self) -> Dict[str, Any]:
        """Return /health, or raise BourseBadVersion if the version is not allowed."""
        body = await self.health()
        if body["version"] not in self._allowed:
            raise BourseBadVersion(
                f"gateway version {body['version']!r} not in {list(self._allowed)}"
            )
        return body

    async def quote(self, instrument_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """One quote by id. Returns (quote, meta)."""
        path = "/v1/quote/" + url_quote(str(instrument_id), safe="")
        data, meta = self._envelope(await self._get(path), path)
        self._check_quote(data, path)
        return data, meta

    async def quotes(self, ids: Iterable[str]) -> Tuple[list, list, Dict[str, Any]]:
        """Up to 200 quotes. Returns (found, missing, meta)."""
        id_list = [str(i) for i in ids]
        if not id_list or len(id_list) > 200:
            raise ValueError("ids must contain 1 to 200 items")
        body = await self._get("/v1/quotes", {"ids": ",".join(id_list)})
        data, meta = self._envelope(body, "/v1/quotes")
        if not isinstance(data, list):
            raise BourseBadResponse("quotes data is not a list")
        for q in data:
            self._check_quote(q, "/v1/quotes")
        missing = body.get("missing", [])
        if not isinstance(missing, list):
            raise BourseBadResponse("quotes 'missing' is not a list")
        return data, missing, meta

    async def changes(self, since: int = 0) -> Tuple[list, Dict[str, Any]]:
        """Quotes changed after `since`. Returns (quotes, meta); pass meta['seq'] next time."""
        data, meta = self._envelope(
            await self._get("/v1/changes", {"since": int(since)}), "/v1/changes"
        )
        if not isinstance(data, list):
            raise BourseBadResponse("changes data is not a list")
        for q in data:
            self._check_quote(q, "/v1/changes")
        return data, meta

    async def symbols(self, q: str, limit: int = 20, **filters: Any) -> Tuple[list, Dict[str, Any]]:
        params: Dict[str, Any] = {"q": q, "limit": max(1, min(100, int(limit)))}
        params.update({k: v for k, v in filters.items() if v not in (None, "")})
        data, meta = self._envelope(await self._get("/v1/symbols", params), "/v1/symbols")
        if not isinstance(data, list):
            raise BourseBadResponse("symbols data is not a list")
        return data, meta

    async def classification(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data, meta = self._envelope(await self._get("/v1/classification"), "/v1/classification")
        if not isinstance(data, dict):
            raise BourseBadResponse("classification data is not an object")
        return data, meta

    @staticmethod
    def _check_quote(quote: Any, path: str) -> None:
        try:
            validate_quote(quote)
        except MappingError as exc:
            raise BourseBadResponse(f"{path}: {exc}") from exc
