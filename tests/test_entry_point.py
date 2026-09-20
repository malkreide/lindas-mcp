"""The HTTP entry point, exercised end to end — no test called `main()` before.

A container deployment crashed on startup, in a loop, on these two lines in
`main()`:

    mcp.settings.host = host
    mcp.settings.port = port

In mcp 2.x `Settings` carries neither field, so pydantic raised
`ValueError: "Settings" object has no field "host"` before uvicorn was ever
reached. Every unit test stayed green: the whole suite built apps through
`build_http_app` directly and never went through the entry point.

That is the same removal that took `transport_security` off `Settings`, and its
line in `_run_http` was already gone — with a comment explaining why. These two
survived one directory further up, which is what a test on the function that
*uses* the helper cannot catch and a test on the entry point can.

So the seam is `uvicorn.run`, not `_run_http`: patching the helper would leave
exactly the stretch that crashed — `main()` reading the environment, and
`_run_http` assembling security and app — unexecuted. Patching `uvicorn.run`
touches the foreign module rather than a local alias, which the portfolio
otherwise warns against; it is sound here because `uvicorn.run` is the endpoint
under no assertion, not the mechanism being checked, and monkeypatch undoes it.
"""

from __future__ import annotations

import pytest

from lindas_mcp import server


@pytest.fixture
def uvicorn_aufruf(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the `uvicorn.run` call instead of serving, so everything from
    `main()` down to the assembled ASGI app runs for real."""
    import uvicorn

    aufruf: dict = {}

    def fake_run(app, **kwargs) -> None:
        aufruf["app"] = app
        aufruf["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return aufruf


@pytest.mark.parametrize("transport", ["http", "streamable-http", "sse"])
def test_main_reaches_uvicorn_for_every_http_transport(
    transport: str, uvicorn_aufruf: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression proper. With either `mcp.settings` line back in place this
    raises `ValueError` before `uvicorn.run` is called, on all three names."""
    monkeypatch.setenv("LINDAS_MCP_TRANSPORT", transport)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8123")

    server.main()

    assert uvicorn_aufruf, f"uvicorn.run was never reached for transport={transport!r}"
    # Not just "it did not crash": the two values the deleted lines used to
    # carry must arrive at their real destination.
    assert uvicorn_aufruf["kwargs"]["host"] == "0.0.0.0"
    assert uvicorn_aufruf["kwargs"]["port"] == 8123
    assert uvicorn_aufruf["app"] is not None


def test_main_honours_the_loopback_default(
    uvicorn_aufruf: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SEC-016. Reading `HOST` moved nowhere, but it is now the only reader of
    it, so nothing else would notice if the default drifted."""
    monkeypatch.setenv("LINDAS_MCP_TRANSPORT", "http")
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    server.main()

    assert uvicorn_aufruf["kwargs"]["host"] == "127.0.0.1"
    assert uvicorn_aufruf["kwargs"]["port"] == 8000


def test_stdio_is_still_the_default_and_takes_no_http_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counter-control: without it the tests above would pass just as well
    if `main()` sent *every* transport down the HTTP branch."""
    monkeypatch.delenv("LINDAS_MCP_TRANSPORT", raising=False)
    laeufe: list = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: laeufe.append(kwargs))
    monkeypatch.setattr(
        server, "_run_http", lambda *a, **k: pytest.fail("stdio took the HTTP branch")
    )

    server.main()

    assert laeufe == [{"transport": "stdio"}]


def test_settings_carries_neither_host_nor_port() -> None:
    """Why the lines had to go rather than be repaired in place — the sibling of
    `test_assigning_transport_security_to_settings_still_raises` in
    `test_cors.py`. Both fields are gone from the model, not renamed.

    This one is a drift watch on the library, not an assertion about `main()`:
    no change to this repository can fail it. It falls if a future `mcp` brings
    the fields back, which is the day the comment in `main()` stops being true.
    The regression itself is caught by the `uvicorn.run` tests above.
    """
    felder = set(type(server.mcp.settings).model_fields)
    assert {"host", "port"} & felder == set(), felder

    for feld in ("host", "port"):
        with pytest.raises(ValueError, match=feld):
            setattr(server.mcp.settings, feld, "x")


def test_the_container_start_command_matches_the_declared_script() -> None:
    """The Dockerfile ran `python -m lindas_mcp.server`, which loads the module
    twice — `__init__.py` imports `.server`, so the package import puts it in
    `sys.modules` before runpy executes it again as `__main__`. Hence the
    `RuntimeWarning` in every container log and two live `MCPServer` instances.

    What is asserted is the join, not the spelling: whatever `CMD` names has to
    be a console script this distribution actually installs. A `CMD` pointing at
    a script that was renamed or dropped fails only when a container starts,
    which is exactly where this crash was found in the first place.
    """
    import shlex
    from importlib.metadata import entry_points
    from pathlib import Path

    # The installed console scripts, not the `pyproject.toml` table: that is what
    # actually lands on the image's PATH, and reading it needs no `tomllib`
    # (stdlib only from 3.11, while the CI matrix still carries 3.10).
    scripts = {e.name: e.value for e in entry_points(group="console_scripts")}

    wurzel = Path(__file__).resolve().parent.parent
    zeilen = (wurzel / "Dockerfile").read_text().splitlines()
    cmds = [z for z in zeilen if z.startswith("CMD ")]
    assert len(cmds) == 1, f"expected one top-level CMD, found {cmds}"
    # JSON exec form, so shlex reads the token out of `CMD ["name"]`.
    befehl = shlex.split(cmds[0].removeprefix("CMD ").strip("[]"))[0].strip('",')

    assert befehl in scripts, (
        f"Dockerfile CMD runs {befehl!r}, which this distribution does not "
        f"install as a console script"
    )
    assert scripts[befehl] == "lindas_mcp.server:main"
