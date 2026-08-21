"""Retry policy toward LINDAS (ARCH-014): Retry-After, jitter, cap.

Deliberately its own module rather than an addition to ``test_client.py``: that
file installs an autouse ``_no_sleep`` fixture, and a test about *how long* to
wait must not run under a fixture whose whole job is to make waiting free.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
import respx

from lindas_mcp.lindas import client as c

#: Captured before any fixture can patch `asyncio.sleep`.
_REAL_SLEEP = asyncio.sleep

EP = c.ENDPOINT

# Wall-clock numbers for the deadline test below, spread far enough apart that
# scheduler jitter cannot move the outcome. Measured on 3.11 over 15 runs of
# that test's own body, through pytest so every fixture is in place:
# 0.121-0.172s against a 0.05s budget. Building and closing the client accounts
# for about 0.075s of that — more than the budget itself — so most of what the
# test used to measure was setup, not deadline. The old bound of 0.5s left
# 0.375s of absolute headroom, and CI jitter is absolute, not proportional: in
# swiss-efv-mcp a loaded runner turned 0.105s into 0.55s on 2026-08-21 and tore
# the same assertion there. Raising the budget does not shrink that stall, it
# makes the stall small *relative to* what is measured.
_BUDGET = 0.5
_CUT_BY = 2.5
_SLOW_RESPONSE = 8.0


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
        # Exactly the cap, not "the cap times jitter": capping happens after
        # jitter, otherwise MAX_DELAY_S would not be a bound at all. Equality
        # still discriminates — the bare curve gives 2s here.
        exc = httpx.HTTPStatusError("503", request=None, response=_resp(503, "86400"))
        assert c.retry_delay(1, exc) == c.MAX_DELAY_S

    def test_exponential_ladder_is_capped(self):
        # 2**10 would be 1024s without a cap.
        for _ in range(30):
            assert c.retry_delay(10, None) <= c.MAX_DELAY_S

    def test_the_cap_is_a_real_bound_not_a_midpoint(self):
        """MAX_DELAY_S must hold even when jitter swings up.

        Capping before jitter let a 20s ceiling grow to 30s on the exponential
        path and 25s on the ``Retry-After`` path. Found by a Codex review on
        ``parlament-mcp#35``, on the same pattern.
        """
        exc = httpx.HTTPStatusError("429", request=None, response=_resp(429, "86400"))
        for attempt in range(1, 8):
            for _ in range(20):
                assert c.retry_delay(attempt, None) <= c.MAX_DELAY_S
                assert c.retry_delay(attempt, exc) <= c.MAX_DELAY_S

    def test_delay_is_spread(self):
        """Without jitter every client retries in lockstep. Draws must differ."""
        draws = {c.retry_delay(2, None) for _ in range(30)}
        assert len(draws) > 1, "delay is deterministic — jitter is not applied"
        base = 4.0
        assert all(base * (1 - c.JITTER_SPREAD) <= d <= base * (1 + c.JITTER_SPREAD) for d in draws)


@respx.mock
async def test_retry_after_reaches_the_sleep(monkeypatch):
    """The value the store sent must reach asyncio.sleep, not the curve."""
    slept: list[float] = []

    async def _capture(seconds):
        slept.append(seconds)

    monkeypatch.setattr(c, "_sleep", _capture)
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

    monkeypatch.setattr(c, "_sleep", _capture)
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

    monkeypatch.setattr(c, "_sleep", _capture)
    route = respx.get(EP).mock(return_value=httpx.Response(404))
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError):
            await c.run_query(http, "SELECT ?s WHERE {}")
    assert route.call_count == 1
    assert slept == []


# --- total budget (ARCH-014) ------------------------------------------------


@pytest.fixture
def fake_clock(monkeypatch):
    """A clock that only advances when the client sleeps.

    Without it the budget can never run out in a test: patched-out sleeps take
    no wall-clock time, so ``time.monotonic()`` never moves and every deadline
    holds forever. The test would then pass whatever the budget logic did.
    """
    now = {"t": 1000.0}

    async def _sleep(seconds):
        now["t"] += seconds

    monkeypatch.setattr(c.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(c, "_sleep", _sleep)
    return now


@respx.mock
async def test_budget_cuts_the_ladder_short(fake_clock):
    """Fewer than MAX_ATTEMPTS requests go out once the waits outlast the budget."""
    route = respx.get(EP).mock(side_effect=httpx.ConnectTimeout(""))
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError) as exc_info:
            await c.run_query(http, "SELECT ?s WHERE {}", total_budget=3.0)
    assert route.call_count < c.MAX_ATTEMPTS, "budget did not bound the ladder"
    assert route.call_count >= 1, "the first attempt must always go out"
    assert "budget spent" in str(exc_info.value)
    assert "3s" in str(exc_info.value)


@respx.mock
async def test_full_ladder_runs_when_the_budget_allows(fake_clock):
    """Counter-direction: a wide budget must not cut anything short."""
    route = respx.get(EP).mock(side_effect=httpx.ConnectTimeout(""))
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError) as exc_info:
            await c.run_query(http, "SELECT ?s WHERE {}", total_budget=600.0)
    assert route.call_count == c.MAX_ATTEMPTS
    assert "all 4 attempts used" in str(exc_info.value)


@respx.mock
async def test_per_request_timeout_is_clamped_to_the_remaining_budget(fake_clock):
    """A single query may not be granted more time than the budget has left."""
    route = respx.get(EP).mock(
        return_value=httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}})
    )
    async with c.build_client() as http:
        await c.run_query(http, "SELECT ?s WHERE {}", total_budget=4.0)
    sent = route.calls.last.request.extensions["timeout"]
    assert sent["read"] == pytest.approx(4.0), sent


@respx.mock
async def test_explicit_timeout_still_wins_when_it_is_tighter(fake_clock):
    """`timeout_s` is not overridden by the budget — the smaller of the two wins."""
    route = respx.get(EP).mock(
        return_value=httpx.Response(200, json={"head": {"vars": []}, "results": {"bindings": []}})
    )
    async with c.build_client() as http:
        await c.run_query(http, "SELECT ?s WHERE {}", timeout_s=2.0, total_budget=600.0)
    sent = route.calls.last.request.extensions["timeout"]
    assert sent["read"] == pytest.approx(2.0), sent


def test_budget_deliberately_exceeds_the_mcp_client_default():
    """LINDAS is the portfolio's documented exception — pin it as a decision.

    Sibling servers (`swiss-efv-mcp`, `termdat-mcp`) keep their budget *under*
    `MCP_DEFAULT_TIMEOUT` so the caller is still listening when they answer.
    Here the store's own abort window (60-90s) is the binding constraint: a
    budget under 30s would kill legitimate SPARQL queries that succeed today.

    Asserting the deviation rather than the conformance keeps it a decision on
    the record instead of something that reads like an oversight — and makes a
    later silent tightening fail loudly.
    """
    from mcp.shared._httpx_utils import MCP_DEFAULT_TIMEOUT

    assert c.TOTAL_BUDGET_S > MCP_DEFAULT_TIMEOUT
    assert c.TOTAL_BUDGET_S == c.TIMEOUT_S  # budget matches the per-request ceiling
    assert c.TOTAL_BUDGET_S < 60.0  # stays inside the store's own abort window


@respx.mock
async def test_a_slow_response_is_cut_by_the_wall_clock_deadline():
    """The budget must bind even when the httpx timeout never fires.

    httpx applies its timeout per operation and the read timeout restarts with
    every chunk, so a slowly trickling answer can outlast the total budget
    without any single read timing out.

    Deliberately without ``fake_clock``, and with ``_REAL_SLEEP`` rather than
    ``asyncio.sleep``: a guarantee about real time cannot be refuted by a clock
    or a sleep that has been patched out. That blind spot is why the original
    counter-checks missed this.

    The margins are wide on purpose — see `_BUDGET` above for the measurement
    that set them. Building the client and the first call through it happen
    before the clock starts, so the measured window holds the deadline and
    nothing else.
    """
    import time as real_time

    _EMPTY = {"head": {"vars": []}, "results": {"bindings": []}}

    # Warm-up on the untouched default budget: pays whatever a fresh client and
    # the first call through it cost, outside the window measured below.
    route = respx.get(EP).mock(return_value=httpx.Response(200, json=_EMPTY))
    async with c.build_client() as warm:
        await c.run_query(warm, "SELECT ?s WHERE {}")

    async def _slow(request):
        await _REAL_SLEEP(_SLOW_RESPONSE)
        return httpx.Response(200, json=_EMPTY)

    route.mock(side_effect=_slow)
    async with c.build_client() as http:
        # The clock starts *inside* the context manager: constructing and
        # closing the client cost more than the old 0.05s budget did, and that
        # is setup, not deadline.
        started = real_time.monotonic()
        with pytest.raises(c.UpstreamError):
            await c.run_query(http, "SELECT ?s WHERE {}", total_budget=_BUDGET)
        elapsed = real_time.monotonic() - started

    # Two-sided on purpose. The upper bound is the guarantee: a response that
    # would have taken _SLOW_RESPONSE was cut. The lower bound says the cut came
    # from the budget rather than from something failing straight away — a
    # deadline computed wrong sails through an upper bound alone.
    assert elapsed >= _BUDGET / 2, f"cut too early to be the budget: {elapsed:.3f}s"
    assert elapsed < _CUT_BY, f"deadline did not cut: {elapsed:.2f}s"


# --- Die Naht, und warum sie nicht `asyncio.sleep` ist -----------------------


def test_der_retry_geht_ueber_den_alias():
    """Sonst patchen die Tests eine Naht, die der Code gar nicht benutzt.

    Umgeht das Modul den Alias, bleibt der Patch wirkungslos und die Suite
    wartet die echte Backoff-Leiter ab. Kein Test faellt dabei — sie wird nur
    um ein Vielfaches langsamer, und eine laengere Laufzeit ist kein Signal,
    das jemand liest. Diese Zusicherung macht daraus einen Fehlschlag.
    """
    quelle = inspect.getsource(c)
    assert "await _sleep(" in quelle, "der Retry ruft den Modul-Alias nicht mehr auf"
    assert "await asyncio.sleep(" not in quelle, "der Retry umgeht den Alias"
