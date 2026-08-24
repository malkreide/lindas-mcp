"""SDK-004: the CORS allow-list now names headers instead of a wildcard.

`allow_headers` read `["*", "Mcp-Session-Id"]`, and the wildcard won. Starlette
switches to `allow_all_headers` and mirrors back whatever a browser announces,
so every permitted origin could send any header at all.

The permissiveness is only half the cost. A wildcard also cannot become wrong:
drop a header the protocol needs and nothing turns red. That is why the
portfolio moved to explicit lists — a list is checkable, a wildcard is not.

Real requests against the assembled app, not an inspection of the middleware
stack: asserting that a `CORSMiddleware` object is present would pass with an
empty list, which is precisely the defect.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from lindas_mcp.server import (
    CORS_ALLOW_HEADERS,
    CORS_ROUTING_HEADERS,
    build_http_app,
    build_transport_security,
    configured_origins,
)

ORIGIN = "https://client.example"

# Both transports. A control that holds on one and not the other is worse than
# a missing one: it looks enforced.
ENDPOINTS = {"streamable-http": "/mcp", "sse": "/sse"}


@pytest.fixture(params=["streamable-http", "sse"])
def kind(request) -> str:
    return request.param


@pytest.fixture
def client(kind: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """`ALLOWED_ORIGINS` muss gesetzt sein: die Origins sind jetzt fail-closed,
    ein unkonfigurierter Server laesst gar keinen Browser durch."""
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    return TestClient(build_http_app(kind))


def preflight(client: TestClient, kind: str, request_headers: str, method: str = "POST"):
    """Send a preflight.

    `request_headers` is what the browser announces it intends to send. It has
    to ride on the request rather than be read off the response: Starlette
    answers a preflight naming a header it does not allow with **400 and no
    `Access-Control-Allow-Origin`**.
    """
    return client.options(
        ENDPOINTS[kind],
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": request_headers,
        },
    )


@pytest.mark.parametrize("header", CORS_ALLOW_HEADERS)
def test_every_allow_listed_header_passes_the_preflight(
    client: TestClient, kind: str, header: str
) -> None:
    """One header per request on purpose: announcing all of them at once would
    still pass if only one were allow-listed and Starlette were lenient about
    the rest."""
    resp = preflight(client, kind, header)
    assert resp.status_code == 200, f"preflight announcing {header} was refused"
    assert header.lower() in resp.headers["access-control-allow-headers"].lower()


def test_the_headers_together(client: TestClient, kind: str) -> None:
    """What a browser actually sends: all of them, on the same request."""
    resp = preflight(client, kind, ", ".join(h.lower() for h in CORS_ALLOW_HEADERS))
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN


def test_a_header_nobody_allow_listed_is_refused(client: TestClient, kind: str) -> None:
    """The negative control — and the finding itself.

    Without it every test above would pass against the old wildcard just as
    well. It is the only assurance here that tells a list from "anything goes".
    """
    resp = preflight(client, kind, "x-not-allowed")
    assert resp.status_code == 400, "the allow-list still waves everything through"


def test_the_list_names_every_routing_header_the_sdk_reads() -> None:
    """Held against the SDK's own constants rather than a copy of the spec text.
    `mcp.shared.inbound` is what the server actually classifies a request with,
    so a rename there surfaces as a failing test instead of a browser client
    that stops connecting for no visible reason."""
    from mcp.shared.inbound import (
        MCP_METHOD_HEADER,
        MCP_NAME_HEADER,
        MCP_PROTOCOL_VERSION_HEADER,
    )

    allowed = {h.lower() for h in CORS_ALLOW_HEADERS}
    required = {MCP_METHOD_HEADER, MCP_NAME_HEADER, MCP_PROTOCOL_VERSION_HEADER}
    assert required <= allowed, f"not allow-listed: {sorted(required - allowed)}"
    assert {h.lower() for h in CORS_ROUTING_HEADERS} == required


def test_the_list_names_the_resumption_header() -> None:
    """`Last-Event-ID` resumes a dropped SSE stream. Without it only
    reconnection after packet loss breaks — under load, in production, with no
    test saying anything about it."""
    from mcp.server.streamable_http import LAST_EVENT_ID_HEADER

    assert LAST_EVENT_ID_HEADER in {h.lower() for h in CORS_ALLOW_HEADERS}


def test_the_list_names_the_session_header() -> None:
    from mcp.server.streamable_http import MCP_SESSION_ID_HEADER

    assert MCP_SESSION_ID_HEADER in {h.lower() for h in CORS_ALLOW_HEADERS}


def test_no_wildcard_in_the_allow_list() -> None:
    """The regression this guards against was exactly one character."""
    assert "*" not in CORS_ALLOW_HEADERS


async def test_no_tool_declares_an_mcp_param_header() -> None:
    """`Mcp-Param-*` carries a tool argument as an HTTP header, opted into by an
    `x-mcp-header` annotation on the input schema. CORS has no prefix wildcard,
    so the first tool to use one must name that exact header in
    `CORS_ALLOW_HEADERS` or browser clients break on it."""
    from lindas_mcp.server import mcp

    offenders = [t.name for t in await mcp.list_tools() if "x-mcp-header" in str(t.input_schema)]
    assert not offenders, (
        f"{offenders} declare an Mcp-Param-* header — name it in CORS_ALLOW_HEADERS"
    )


def test_the_http_app_carries_the_transport_security(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mcp.settings.transport_security = security` used to stand in `_run_http`.

    In mcp 2.x that field does not exist: pydantic raises `ValueError: "Settings"
    object has no field "transport_security"`, so every HTTP transport died on
    that line before uvicorn was reached. It is a per-app keyword argument now.

    Asserting that `build_http_app` merely *accepts* the argument would not be
    enough — a parameter that is taken and dropped looks identical. So the check
    is behavioural: a foreign `Host` must be refused with 421, and it only is
    when the object actually reaches the app.
    """
    monkeypatch.setenv("LINDAS_MCP_ALLOWED_HOSTS", "mcp.example.ch")
    security = build_transport_security("0.0.0.0", 8000)
    assert security is not None

    def host_status(sicherheit) -> int:
        with TestClient(build_http_app("streamable-http", sicherheit, "0.0.0.0")) as c:
            return c.post(
                "/mcp",
                headers={
                    "Host": "evil.example",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={},
            ).status_code

    assert host_status(security) == 421, "foreign Host was not refused"
    # The negative control: without the object the same request gets past the
    # Host check and dies later, on the empty JSON-RPC body.
    assert host_status(None) == 400


def test_no_configured_origin_means_no_browser_access(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed. the default was `*`, so every website on the
    internet could call this server from a visitor's browser unless an operator
    knew to narrow it. "Frictionless in dev" and "open to the internet in
    production" were the same setting.

    Unset now means no cross-origin access at all. stdio and non-browser
    clients are unaffected — CORS governs browsers only.
    """
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    client = TestClient(build_http_app(kind))
    resp = preflight(client, kind, "content-type")
    assert "access-control-allow-origin" not in resp.headers


def test_an_origin_outside_the_list_is_refused(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The counter-control. Without it every origin test here would pass just
    as well against the old wildcard."""
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    client = TestClient(build_http_app(kind))
    resp = client.options(
        ENDPOINTS[kind],
        headers={
            "Origin": "https://elsewhere.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


def test_the_wildcard_is_still_reachable_but_must_be_asked_for(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tightening a default is not the same as removing the option. An operator
    who wants any-origin access can still have it — deliberately, and the
    server logs a warning when they do."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    client = TestClient(build_http_app(kind))
    resp = preflight(client, kind, "content-type")
    assert resp.headers["access-control-allow-origin"] == "*"


def test_configured_origins_parses_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.test , https://b.test ")
    assert configured_origins() == ["https://a.test", "https://b.test"]


def test_the_transport_check_lets_the_configured_origins_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Konfigurierte Origins muessen auch die Transport-Pruefung passieren,
    sonst weist der Server genau die Browser-Clients ab, die CORS erlaubt.
    Beide Stellen lesen jetzt dieselbe Funktion statt zweier Parser.
    """
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.test,*")
    security = build_transport_security("127.0.0.1", 8000)
    assert security is not None
    assert "https://a.test" in security.allowed_origins
    # `*` is not expressible there (origins are matched literally).
    assert "*" not in security.allowed_origins


def test_assigning_transport_security_to_settings_still_raises() -> None:
    """Why the line had to move rather than be repaired in place."""
    from lindas_mcp.server import mcp

    with pytest.raises(ValueError, match="transport_security"):
        mcp.settings.transport_security = None
