"""Inbound Host/Origin validation on the HTTP/SSE transports (SEC-005).

The SDK leaves DNS-rebinding protection off while ``transport_security`` is
unset. This server never set it, so there was no Host check at all. These tests
pin the new behaviour and fail if the protection is dropped again.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from lindas_mcp.server import build_transport_security, mcp

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def test_loopback_bind_enables_protection(monkeypatch):
    monkeypatch.delenv("LINDAS_MCP_ALLOWED_HOSTS", raising=False)
    sec = build_transport_security("127.0.0.1", 8000)
    assert sec is not None
    assert sec.enable_dns_rebinding_protection is True
    assert "127.0.0.1:8000" in sec.allowed_hosts
    assert "localhost:8000" in sec.allowed_hosts


def test_non_local_bind_without_allowlist_stays_off(monkeypatch):
    """0.0.0.0 with no allow-list: the reachable name is unknowable here, so a
    guess would reject every real request. Protection stays off; caller warns."""
    monkeypatch.delenv("LINDAS_MCP_ALLOWED_HOSTS", raising=False)
    assert build_transport_security("0.0.0.0", 8000) is None


def test_non_local_bind_with_allowlist_enables_protection(monkeypatch):
    monkeypatch.setenv("LINDAS_MCP_ALLOWED_HOSTS", "mcp.example.ch,mcp.example.ch:443")
    sec = build_transport_security("0.0.0.0", 8000)
    assert sec is not None
    assert "mcp.example.ch" in sec.allowed_hosts
    # Loopback stays in, otherwise container health checks break.
    assert "127.0.0.1:8000" in sec.allowed_hosts


def test_port_is_honoured(monkeypatch):
    monkeypatch.delenv("LINDAS_MCP_ALLOWED_HOSTS", raising=False)
    sec = build_transport_security("127.0.0.1", 9443)
    assert "127.0.0.1:9443" in sec.allowed_hosts
    assert "127.0.0.1:8000" not in sec.allowed_hosts


def test_wildcard_is_not_copied_into_allowed_origins(monkeypatch):
    """"*" is matched literally by the SDK, so copying it would look like a
    wildcard while doing nothing."""
    monkeypatch.delenv("LINDAS_MCP_ALLOWED_HOSTS", raising=False)
    sec = build_transport_security("127.0.0.1", 8000)
    assert "*" not in sec.allowed_origins
    # The derived loopback origins must still be present, or a same-host
    # browser request would be refused.
    assert "http://127.0.0.1:8000" in sec.allowed_origins


def _post_with_host(host_header: str):
    mcp.settings.transport_security = build_transport_security("127.0.0.1", 8000)
    # The SDK caches the session manager on the instance and only lets it run
    # once; without this reset the second app build fails in the lifespan.
    mcp._session_manager = None
    with TestClient(mcp.streamable_http_app()) as client:
        return client.post("/mcp", headers={"Host": host_header, **_HEADERS}, json=_INIT)


def test_allowed_host_is_served():
    assert _post_with_host("127.0.0.1:8000").status_code == 200


def test_foreign_host_is_rejected():
    assert _post_with_host("evil.example.com").status_code == 421


def test_right_host_wrong_port_is_rejected():
    """The load-bearing case: a fallback localhost policy would also reject
    ``evil.example.com``, so only right-hostname/wrong-port proves the
    port-precise allow-list is really installed."""
    assert _post_with_host("127.0.0.1:9999").status_code == 421


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_all_loopback_forms_are_local(host, monkeypatch):
    monkeypatch.delenv("LINDAS_MCP_ALLOWED_HOSTS", raising=False)
    assert build_transport_security(host, 8000) is not None
