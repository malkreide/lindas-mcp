"""Die moderne Aera (Spec 2026-07-28), gemessen durch den echten Stack.

`test_protocol_version.py` pinnt die beiden Revisionen und faehrt einen echten
`initialize` — aber nur den. Die moderne Aera stand damit in beiden READMEs und
in keinem Test: waere der Pro-Request-Pfad vollstaendig kaputt gewesen, waere
nichts rot geworden. Diese Datei schliesst die Luecke; die Aufteilung ist
bewusst, `test_protocol_version.py` bleibt der Ort der Revisions-Pins.

Was hier *nicht* gemessen wird, weil es das SDK besitzt und nicht dieser
Server: die Umsetzung der Ladder selbst. Gemessen wird, dass dieser Server —
mit seinem Lifespan, seinem CORS-Wrapper und seinen sieben Werkzeugen — die
moderne Aera tatsaechlich bedient, in beiden Transporten, und mit welcher
Identitaet er das tut.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest
import respx
from fixture_data import fixture_text
from mcp_types.jsonrpc import (
    HEADER_MISMATCH,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    UNSUPPORTED_PROTOCOL_VERSION,
)

from lindas_mcp._version import __version__
from lindas_mcp.server import build_http_app

REPO = Path(__file__).resolve().parents[1]

MODERN = "2026-07-28"

PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"

ENVELOPE = {
    PROTOCOL_VERSION_KEY: MODERN,
    CLIENT_CAPABILITIES_KEY: {},
    CLIENT_INFO_KEY: {"name": "spec-test", "version": "1"},
}

_BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Host": "127.0.0.1:8000",
}


async def _modern_post(
    method: str,
    params: dict | None = None,
    *,
    envelope: dict | None = ENVELOPE,
    headers: dict | None = None,
) -> httpx.Response:
    """Eine moderne Anfrage durch den zusammengebauten ASGI-Stack.

    `envelope=None` laesst `params._meta` weg — so laesst sich pruefen, dass
    der Envelope Pflicht ist und nicht bloss geduldet wird. `headers`
    ueberschreibt die abgeleiteten Routing-Header, fuer die Mismatch-Faelle.
    """
    body: dict = {"jsonrpc": "2.0", "id": 1, "method": method, "params": dict(params or {})}
    if envelope is not None:
        body["params"]["_meta"] = envelope

    sent = dict(_BASE_HEADERS)
    sent["MCP-Protocol-Version"] = MODERN
    sent["Mcp-Method"] = method
    name = (params or {}).get("name")
    if method == "tools/call" and name is not None:
        sent["Mcp-Name"] = name
    sent.update(headers or {})

    app = build_http_app("streamable-http")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
            return await client.post("/mcp", headers=sent, json=body)


def _payload(response: httpx.Response) -> dict:
    """JSON-RPC-Nutzlast, SSE-Rahmen abgestreift, falls vorhanden."""
    text = response.text
    for line in text.splitlines():
        if line.startswith("data: "):
            text = line[len("data: ") :]
    return json.loads(text)


# --------------------------------------------------------------------------
# Die Aera wird tatsaechlich bedient
# --------------------------------------------------------------------------


async def test_discover_nennt_genau_die_moderne_revision() -> None:
    """`server/discover` ist der Einstieg der modernen Aera — es gibt keinen
    Handshake, durch den ein Client sonst erfuehre, was hier gesprochen wird."""
    response = await _modern_post("server/discover")
    assert response.status_code == 200, response.text
    result = _payload(response)["result"]
    assert result["supportedVersions"] == [MODERN]


async def test_discover_traegt_die_orientierung_fuer_die_moderne_aera() -> None:
    """In der modernen Aera gibt es kein `initialize`-Ergebnis, in dem
    `instructions` stehen koennten. `server/discover` ist der einzige Kanal —
    leer gelassen bekommt ein moderner Client den Zwei-Phasen-Zugriff nirgends
    zu lesen und liest Beobachtungen ohne die Struktur."""
    result = _payload(await _modern_post("server/discover"))["result"]
    instructions = result.get("instructions")
    assert instructions, "server/discover liefert keine instructions"
    assert "get_cube_structure" in instructions


@pytest.mark.parametrize("method", ["server/discover", "tools/list"])
async def test_jede_moderne_antwort_stempelt_eine_echte_version(method: str) -> None:
    """Der lasttragende Fall dieser Datei.

    `MCPServer` deckt `version` mit `""` vor und setzt nichts eigenes ein. Ohne
    Zutun trug also jede Antwort `{"name": "lindas-mcp", "version": ""}` —
    formal ein Pflichtfeld, inhaltlich nichts. In der modernen Aera ist dieser
    Stempel die einzige Stelle, an der ein Client die Version erfaehrt.

    Gegen `__version__` gepruefte Gleichheit, nicht gegen ein Literal: eine
    Zahl hier waere die zweite Kopie, die `check_version_sync.py` in `src/`
    gerade verbietet.
    """
    payload = _payload(await _modern_post(method))
    server_info = payload["result"]["_meta"][SERVER_INFO_KEY]
    assert server_info["name"] == "lindas-mcp"
    assert server_info["version"] == __version__
    assert server_info["version"] != ""


async def test_der_stempel_nennt_herkunft_und_zweck() -> None:
    """`title`, `description` und `websiteUrl` sind die uebrigen Felder von
    `Implementation`. Sie einzeln zu pruefen unterscheidet «Identitaet
    gesetzt» von «Versionsnummer gesetzt»."""
    payload = _payload(await _modern_post("server/discover"))
    server_info = payload["result"]["_meta"][SERVER_INFO_KEY]
    assert "LINDAS" in server_info["title"]
    assert server_info["description"]
    assert server_info["websiteUrl"].startswith("https://")


async def test_die_werkzeuge_sind_in_beiden_aeren_dieselben() -> None:
    """Eine moderne Aera, die eine andere Werkzeugliste bedient als die
    Handshake-Aera, waere ein zweiter Server unter derselben Adresse.

    Verglichen wird gegen `tool-definitions.lock.json` — dieselbe Quelle, an
    der SEC-022 die Handshake-Seite festnagelt.
    """
    lock = json.loads((REPO / "tool-definitions.lock.json").read_text(encoding="utf-8"))
    erwartet = sorted(t["name"] for t in lock["tools"])

    result = _payload(await _modern_post("tools/list"))["result"]
    assert sorted(t["name"] for t in result["tools"]) == erwartet


@respx.mock
async def test_ein_werkzeug_laeuft_durch_den_pro_request_envelope() -> None:
    """Nicht bloss auflisten: ein echter `tools/call` durch den modernen Pfad.

    Ohne diesen Fall waere jede Zusicherung oben auch gegen einen Server gruen,
    der nur Verzeichnisse bedient — und genau der Weg, auf dem Daten fliessen,
    bliebe ungemessen.

    Die Antwort kommt aus der Aufzeichnung (`list_creators.json`), nicht aus
    einem Stub: ein handgeschriebener Koerper belegte nur, dass der Envelope
    einen Pfad oeffnet, den der Autor sich vorgestellt hat.
    """
    respx.route(host="lindas.admin.ch").mock(
        return_value=httpx.Response(200, text=fixture_text("list_creators.json"))
    )
    response = await _modern_post("tools/call", {"name": "list_publishers", "arguments": {}})
    assert response.status_code == 200, response.text
    result = _payload(response)["result"]
    assert result.get("isError") is not True, result
    assert result["structuredContent"]["publishers"], result


# --------------------------------------------------------------------------
# Der Envelope ist Pflicht, und die Header muessen zum Koerper passen
# --------------------------------------------------------------------------


async def test_ohne_envelope_keine_moderne_antwort() -> None:
    """Sonst liesse sich «die moderne Aera wird bedient» auch dadurch
    erfuellen, dass der Server den Envelope ignoriert."""
    response = await _modern_post("tools/list", envelope=None)
    assert response.status_code == 400
    assert _payload(response)["error"]["code"] == INVALID_PARAMS


async def test_ein_widerspruechlicher_methoden_header_wird_abgewiesen() -> None:
    """Spec 2026-07-28 routet per Header; weicht er vom Koerper ab, darf keine
    der beiden Lesarten gewinnen. `CORS_ALLOW_HEADERS` laesst diese Header
    durch — dass sie auch geprueft werden, steht erst hier."""
    response = await _modern_post("tools/list", headers={"Mcp-Method": "tools/call"})
    assert response.status_code == 400
    assert _payload(response)["error"]["code"] == HEADER_MISMATCH


async def test_ein_widerspruechlicher_name_header_wird_abgewiesen() -> None:
    """Derselbe Schutz eine Ebene tiefer: `Mcp-Name` nennt das Werkzeug. Ohne
    diesen Fall bliebe unbelegt, dass mehr als der Methoden-Header geprueft
    wird."""
    response = await _modern_post(
        "tools/call",
        {"name": "list_publishers", "arguments": {}},
        headers={"Mcp-Name": "run_sparql"},
    )
    assert response.status_code == 400
    assert _payload(response)["error"]["code"] == HEADER_MISMATCH


async def test_eine_unbekannte_revision_bekommt_die_liste_der_bekannten() -> None:
    """Eine Absage, die nicht sagt, was ginge, liest sich fuer das Modell wie
    eine Stoerung — derselbe Fehler wie ein Wiederholungsrat auf einen 400er."""
    envelope = {**ENVELOPE, PROTOCOL_VERSION_KEY: "2099-01-01"}
    response = await _modern_post(
        "tools/list", envelope=envelope, headers={"MCP-Protocol-Version": "2099-01-01"}
    )
    error = _payload(response)["error"]
    assert error["code"] == UNSUPPORTED_PROTOCOL_VERSION
    assert error["data"]["supported"] == [MODERN]
    assert error["data"]["requested"] == "2099-01-01"


async def test_der_handshake_ist_auf_dem_modernen_pfad_nicht_erreichbar() -> None:
    """Die Gegenrichtung zu `test_protocol_version.py`: dort wird gemessen,
    dass der Handshake bei `2025-11-25` deckelt. Hier, dass `initialize` auf
    dem Pro-Request-Pfad gar nicht erst existiert — sonst waeren die beiden
    Aeren nicht getrennt, sondern vermischt."""
    response = await _modern_post(
        "initialize",
        {
            "protocolVersion": MODERN,
            "capabilities": {},
            "clientInfo": {"name": "x", "version": "1"},
        },
    )
    assert response.status_code == 404
    assert _payload(response)["error"]["code"] == METHOD_NOT_FOUND


# --------------------------------------------------------------------------
# stdio — der Standard-Transport dieses Servers
# --------------------------------------------------------------------------


def test_stdio_bedient_die_moderne_aera_ebenfalls() -> None:
    """`LINDAS_MCP_TRANSPORT` steht standardmaessig auf stdio, und alle Faelle
    oben fahren HTTP. Ohne diesen Test waere die moderne Aera genau auf dem
    Transport ungemessen, ueber den dieser Server ueblicherweise laeuft.

    Ein Unterprozess statt eines Aufrufs in-process: gemessen werden soll der
    Einstiegspunkt mitsamt `main()` und Transportwahl, nicht eine von Hand
    zusammengesetzte Schleife.

    stdin bleibt bis zur Antwort offen. Wird es sofort geschlossen, gewinnt das
    EOF gegen die Antwort und der Test misst die Abbruchreihenfolge statt der
    Aera — beim Schreiben genau so passiert.
    """
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO / "src"),
        "LINDAS_MCP_TRANSPORT": "stdio",
        "LOG_LEVEL": "CRITICAL",
    }
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "server/discover",
        "params": {"_meta": ENVELOPE},
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "lindas_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None

    # Gelesen wird in einem Thread mit Frist. `readline()` direkt blockiert
    # ohne Obergrenze: ein Server, der gar nichts schreibt, liesse die CI
    # haengen statt rot zu werden — der teuerste Fehlschlag von allen, weil er
    # nicht sagt, was los ist.
    gelesen: list[str] = []
    leser = threading.Thread(target=lambda: gelesen.append(proc.stdout.readline()))
    leser.daemon = True
    try:
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        leser.start()
        leser.join(timeout=30)
        proc.stdin.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=30)

    stderr = proc.stderr.read()[-2000:] if proc.stderr is not None else ""
    assert gelesen, f"keine Antwort binnen 30 s; stderr: {stderr}"
    assert gelesen[0], f"stdout ohne Inhalt geschlossen; stderr: {stderr}"

    result = json.loads(gelesen[0])["result"]
    assert result["supportedVersions"] == [MODERN]
    assert result["_meta"][SERVER_INFO_KEY]["version"] == __version__


# --------------------------------------------------------------------------
# Log-Zustellung: auf 2026-07-28 eine Anmeldung pro Anfrage
# --------------------------------------------------------------------------

LOG_LEVEL_KEY = "io.modelcontextprotocol/logLevel"


async def _tools_call_mit_log_anmeldung(level: str | None) -> httpx.Response:
    """`list_publishers` ueber den modernen Pfad, wahlweise mit Log-Anmeldung."""
    envelope = dict(ENVELOPE)
    if level is not None:
        envelope[LOG_LEVEL_KEY] = level
    respx.route(host="lindas.admin.ch").mock(
        return_value=httpx.Response(200, text=fixture_text("list_creators.json"))
    )
    return await _modern_post(
        "tools/call", {"name": "list_publishers", "arguments": {}}, envelope=envelope
    )


def _log_eintraege(response: httpx.Response) -> list[dict]:
    """Die `notifications/message`-Rahmen aus einer SSE-Antwort."""
    eintraege = []
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        frame = json.loads(line[len("data: ") :])
        if frame.get("method") == "notifications/message":
            eintraege.append(frame["params"])
    return eintraege


@respx.mock
async def test_ohne_anmeldung_kein_log_auf_dem_draht() -> None:
    """Spec 2026-07-28 kehrt die Voreinstellung um: ohne den reservierten
    `_meta`-Schluessel DARF der Server nichts senden. `logging/setLevel`, mit
    dem ein Client das frueher einmalig einstellte, gibt es nicht mehr.

    Das ist die Gegenprobe zum Test darunter: ohne sie waere «der Eintrag
    kommt an» auch gegen einen Server gruen, der ihn jedem aufdraengt.
    """
    response = await _tools_call_mit_log_anmeldung(None)
    assert response.status_code == 200, response.text
    assert _log_eintraege(response) == []


@respx.mock
async def test_mit_anmeldung_kommt_der_eintrag_an() -> None:
    """Und die Richtung, die begruendet, warum `_log_call` den als veraltet
    markierten `ctx.debug` weiter aufruft: auf der Zielrevision ist das der
    vorgesehene Weg, sobald der Client danach fragt. Waere der Aufruf
    entfernt, faellt genau dieser Test.
    """
    response = await _tools_call_mit_log_anmeldung("debug")
    assert response.status_code == 200, response.text
    eintraege = _log_eintraege(response)
    assert len(eintraege) == 1, response.text
    assert eintraege[0]["level"] == "debug"
    assert "list_publishers" in eintraege[0]["data"]
