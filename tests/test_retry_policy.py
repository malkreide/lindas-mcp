"""Retry policy toward LINDAS (ARCH-014): Retry-After, jitter, cap.

Deliberately its own module rather than an addition to ``test_client.py``: that
file installs an autouse ``_no_sleep`` fixture, and a test about *how long* to
wait must not run under a fixture whose whole job is to make waiting free.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
import respx

from lindas_mcp.lindas import client as c

EP = c.ENDPOINT


def _resp(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", EP))


class TestParseRetryAfter:
    def test_delta_seconds(self):
        assert c.parse_retry_after(_resp(429, "120")) == 120.0

    def test_http_date_in_the_future(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=90)
        got = c.parse_retry_after(_resp(503, format_datetime(when, usegmt=True)))
        assert got is not None
        assert 80 <= got <= 95  # second-resolution header, allow slack

    def test_http_date_in_the_past_means_now(self):
        when = datetime.now(timezone.utc) - timedelta(hours=1)
        assert c.parse_retry_after(_resp(503, format_datetime(when, usegmt=True))) == 0.0

    def test_absent_header(self):
        assert c.parse_retry_after(_resp(429)) is None

    def test_malformed_header_does_not_raise(self):
        # A bad header must not turn into a crash on the error path.
        assert c.parse_retry_after(_resp(429, "next Tuesday")) is None
        assert c.parse_retry_after(_resp(429, "")) is None
        assert c.parse_retry_after(_resp(429, "-5")) is None

    def test_ignored_on_other_statuses(self):
        assert c.parse_retry_after(_resp(500, "30")) is None

    def test_no_response_at_all(self):
        # Timeouts and connect errors carry no response object.
        assert c.parse_retry_after(None) is None


class TestRetryDelay:
    def test_retry_after_beats_the_exponential_curve(self):
        # The hinted value sits outside the curve's reach: attempt 1 spans
        # [1, 3] seconds, so a delay near 9 can only come from the header.
        exc = httpx.HTTPStatusError("429", request=None, response=_resp(429, "9"))
        assert 9.0 <= c.retry_delay(1, exc) <= 9.0 * (1 + c.RETRY_AFTER_JITTER)

    def test_retry_after_is_never_undercut(self):
        """One-sided jitter: later is polite, earlier ignores what we just read."""
        exc = httpx.HTTPStatusError("429", request=None, response=_resp(429, "5"))
        for _ in range(50):
            assert c.retry_delay(1, exc) >= 5.0

    def test_absurd_retry_after_is_capped(self):
        # Both bounds matter: the upper proves the cap binds, the lower proves
        # the header was read at all — without it the curve's 2s would pass.
        exc = httpx.HTTPStatusError("503", request=None, response=_resp(503, "86400"))
        delay = c.retry_delay(1, exc)
        assert c.MAX_DELAY_S <= delay <= c.MAX_DELAY_S * (1 + c.RETRY_AFTER_JITTER)

    def test_exponential_ladder_is_capped(self):
        # 2**10 would be 1024s without a cap.
        assert c.retry_delay(10, None) <= c.MAX_DELAY_S * (1 + c.JITTER_SPREAD)

    def test_delay_is_spread(self):
        """Without jitter every client retries in lockstep. Draws must differ."""
        draws = {c.retry_delay(2, None) for _ in range(30)}
        assert len(draws) > 1, "delay is deterministic — jitter is not applied"
        base = 4.0
        assert all(
            base * (1 - c.JITTER_SPREAD) <= d <= base * (1 + c.JITTER_SPREAD) for d in draws
        )


@respx.mock
async def test_retry_after_reaches_the_sleep(monkeypatch):
    """The value the store sent must reach asyncio.sleep, not the curve."""
    slept: list[float] = []

    async def _capture(seconds):
        slept.append(seconds)

    monkeypatch.setattr(c.asyncio, "sleep", _capture)
    respx.get(EP).mock(
        side_effect=[
            _resp(429, "7"),
            httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}}),
        ]
    )
    async with c.build_client() as http:
        await c.run_query(http, "SELECT ?s WHERE {}")
    assert len(slept) == 1
    assert 7.0 <= slept[0] <= 7.0 * (1 + c.RETRY_AFTER_JITTER)


@respx.mock
async def test_429_without_header_falls_back_to_the_curve(monkeypatch):
    slept: list[float] = []

    async def _capture(seconds):
        slept.append(seconds)

    monkeypatch.setattr(c.asyncio, "sleep", _capture)
    respx.get(EP).mock(
        side_effect=[
            _resp(429),
            httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}}),
        ]
    )
    async with c.build_client() as http:
        await c.run_query(http, "SELECT ?s WHERE {}")
    assert len(slept) == 1
    assert 2.0 * (1 - c.JITTER_SPREAD) <= slept[0] <= 2.0 * (1 + c.JITTER_SPREAD)


@respx.mock
async def test_404_still_fails_fast_without_waiting(monkeypatch):
    """4xx except 429 is a statement about the request, not about the moment."""
    slept: list[float] = []

    async def _capture(seconds):
        slept.append(seconds)

    monkeypatch.setattr(c.asyncio, "sleep", _capture)
    route = respx.get(EP).mock(return_value=httpx.Response(404))
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError):
            await c.run_query(http, "SELECT ?s WHERE {}")
    assert route.call_count == 1
    assert slept == []
