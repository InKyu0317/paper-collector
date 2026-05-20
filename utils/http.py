"""Shared HTTP client with retry, timeout, and rate-limiting support.

All API connectors should use this client (or derive from it) to ensure
consistent behavior across different data sources.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class HttpClient:
    """Wraps httpx.AsyncClient with tenacity-based retries.

    Includes a simple token-bucket rate limiter to respect API politeness
    policies.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        user_agent: str = "PaperCollector/0.1",
        rate_limit_delay: float = 0.0,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    # ── Rate limiting ─────────────────────────────────────────────

    def _apply_rate_limit(self) -> None:
        if self.rate_limit_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    # ── HTTP methods ──────────────────────────────────────────────

    def get(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        self._apply_rate_limit()
        response = self._retry_get(url, params=params, headers=headers)
        response.raise_for_status()
        return response

    def get_json(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        return self.get(url, params=params, headers=headers).json()

    def download_bytes(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
    ) -> bytes:
        self._apply_rate_limit()
        response = self._retry_get(url, headers=headers)
        response.raise_for_status()
        return response.content

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def _retry_get(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        return self._client.get(url, params=params, headers=headers)

    # ── Lifecycle ─────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
