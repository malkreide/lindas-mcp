#!/usr/bin/env python3
"""Zeichnet echte LINDAS-Antworten nach `tests/fixtures/` auf.

Warum: eine handgeschriebene Fixture kodiert die Annahme ihres Autors und kann
sie deshalb nicht widerlegen. In `i14y-mcp` blieb genau deshalb eine ganze Suite
gruen, waehrend drei Tools produktiv leere Titel lieferten — die Stubs hatten
einen Schluessel erfunden und stimmten dem Mapper zu statt der Quelle.

Dieser Server spricht mit **einem** Endpunkt, aber in sieben Abfrageformen. Die
Form der Antwort haengt an der Abfrage, nicht am Endpunkt: `cube_dimensions`
liefert andere Variablen als `cube_observations`, und ein Stub, der beide gleich
raet, faellt nie auf. Aufgezeichnet wird deshalb eine Antwort **je Abfrageform**.

Aufgezeichnet wird die **rohe SPARQL-JSON-Antwort**, nicht das geparste
Ergebnis: `_parse_bindings` ist Teil dessen, was geprueft werden soll. Eine
Fixture aus geparsten Zeilen wuerde den Parser ueberspringen, den sie belegen
soll.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei schreibt dieses Skript nach
`tests/fixtures/PROVENANCE.md`. Neu aufzeichnen:

    PYTHONPATH=src python scripts/record_fixtures.py

Braucht Netzzugang zu `lindas.admin.ch`. Entwicklungswerkzeug; weder das Paket
noch die Testsuite importieren es.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from lindas_mcp.lindas import client as c
from lindas_mcp.lindas import queries as q

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# Fest gewaehlt, nicht «irgendeiner»: eine vom Lauf abhaengige Auswahl erzeugt
# bei jedem Aufzeichnen einen anderen Diff.
SUCHBEGRIFF = "bevölkerung"
SPRACHE = "de"
GEMEINDE = "Winterthur"
BFS_NUMMER = 230  # Winterthur — dieselbe Gemeinde wie oben, ueber den zweiten Weg
LIMIT = 5


async def hole_roh(http: httpx.AsyncClient, query: str) -> tuple[str, str]:
    """Fuehrt eine Abfrage aus und liefert (Antworttext, angefragte URL).

    Bewusst nicht ueber `run_query`: das liefert geparste Zeilen zurueck, und
    aufgezeichnet werden soll die Antwort, wie sie ankommt. Der Weg (GET oder
    POST) folgt derselben Laengenregel wie im Client, damit die Aufzeichnung
    denselben Pfad belegt, den der Server geht.
    """
    if len(query) > c.GET_QUERY_LIMIT:
        resp = await http.post(
            c.ENDPOINT,
            content=query.encode("utf-8"),
            headers={"Content-Type": "application/sparql-query"},
            timeout=90,
        )
    else:
        resp = await http.get(c.ENDPOINT, params={"query": query}, timeout=90)
    resp.raise_for_status()
    return resp.text, str(resp.url)


async def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d")
    entries: list[dict[str, Any]] = []
    print(f"Zeichne auf von {c.ENDPOINT}")

    def write(name: str, text: str, url: str, rule: str, zeilen: int) -> None:
        blob = text.encode("utf-8")
        (FIXTURES / name).write_bytes(blob)
        entries.append(
            {
                "name": name,
                "url": url,
                "rule": rule,
                "bytes": len(blob),
                "zeilen": zeilen,
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
        print(f"  ok  {name:<28} {len(blob):>7} B  ({zeilen} Zeilen)")

    async with c.client_session() as http:
        # --- Die Suche, und der Wuerfel, an dem alles Weitere haengt --------
        suche = q.search_cubes(SUCHBEGRIFF, SPRACHE, None, LIMIT)
        text, url = await hole_roh(http, suche)
        treffer = c._parse_bindings(json.loads(text))
        assert treffer, "die Suche liefert nichts — Begriff pruefen"
        wuerfel = treffer[0]["cube"]
        write(
            "search_cubes.json",
            text,
            url,
            f"vollstaendig; Suche nach {SUCHBEGRIFF!r}, limit {LIMIT}. Der erste "
            f"Treffer ({wuerfel}) ist der Wuerfel aller folgenden Aufzeichnungen "
            "— sie beschreiben damit **denselben** Gegenstand und nicht sieben "
            "zufaellige",
            len(treffer),
        )

        # --- Die uebrigen Abfrageformen, alle am selben Wuerfel -------------
        formen = (
            ("cube_metadata.json", q.cube_metadata(wuerfel, SPRACHE), "Metadaten des Wuerfels"),
            (
                "cube_dimensions.json",
                q.cube_dimensions(wuerfel, SPRACHE),
                "Dimensionen des Wuerfels — andere Variablen als jede andere Form",
            ),
            (
                "cube_observations.json",
                q.cube_observations(wuerfel, LIMIT),
                f"{LIMIT} Beobachtungen als Tripel (`obs`/`p`/`o`); der Server "
                "dreht sie erst danach in Zeilen",
            ),
            (
                "list_creators.json",
                q.list_creators(),
                "vollstaendig; alle Herausgeber mit Wuerfelzahl",
            ),
            (
                "municipality_by_name.json",
                q.resolve_municipality_by_name(GEMEINDE, SPRACHE),
                f"Gemeinde {GEMEINDE!r} ueber den Namen",
            ),
            (
                "municipality_by_bfs.json",
                q.resolve_municipality_by_bfs(BFS_NUMMER),
                f"BFS-Nummer {BFS_NUMMER} — **dieselbe** Gemeinde wie oben, ueber "
                "den zweiten Weg. Damit belegt das Paar, dass beide Wege "
                "denselben Datensatz treffen",
            ),
        )
        for name, query, regel in formen:
            text, url = await hole_roh(http, query)
            zeilen = len(c._parse_bindings(json.loads(text)))
            write(name, text, url, f"vollstaendig; {regel}", zeilen)

        # --- Eine Codeliste, wenn der Wuerfel eine fuehrt -------------------
        dims = c._parse_bindings(
            json.loads((await hole_roh(http, q.cube_dimensions(wuerfel, SPRACHE)))[0])
        )

        # `has_codelist` kommt als **String** aus SPARQL: "true" oder "false".
        # Ein blosses `if d.get("has_codelist")` ist damit immer wahr — auch bei
        # "false". Der Server weiss das (`cube.py` wandelt ausdruecklich um);
        # dieser Recorder hat es beim ersten Lauf nicht gewusst und eine leere
        # Codeliste aufgezeichnet. Gelesen wird deshalb wie dort.
        def hat_codeliste(d: dict[str, Any]) -> bool:
            return str(d.get("has_codelist", "")).lower() in {"true", "1"}

        mit_liste = next((d for d in dims if hat_codeliste(d)), None)
        if mit_liste is not None:
            text, url = await hole_roh(
                http, q.dimension_codelist(wuerfel, mit_liste["path"], SPRACHE)
            )
            zeilen = len(c._parse_bindings(json.loads(text)))
            assert zeilen, (
                f"die Codeliste von {mit_liste['path']} ist leer — eine leere "
                "Fixture sieht aus wie eine gueltige und prueft nichts"
            )
            write(
                "dimension_codelist.json",
                text,
                url,
                "vollstaendig; die Codeliste der ersten Dimension des Wuerfels, "
                f"die eine fuehrt ({mit_liste['path']}). Ohne sie bleibt die "
                "Code-zu-Label-Aufloesung ungeprueft",
                zeilen,
            )
        else:
            print("  !! kein Wuerfel mit Codeliste gefunden — Auswahlregel pruefen")

    _write_provenance(recorded_at, entries)
    print(f"\nPROVENANCE.md geschrieben, Aufzeichnungsdatum {recorded_at}")
    return _warne_bei_ignorierten(entries)


def _warne_bei_ignorierten(entries: list[dict[str, Any]]) -> int:
    """Meldet Aufzeichnungen, die `.gitignore` ausschliesst.

    Eine ignorierte Fixture faellt lokal nicht auf — die Datei liegt ja da und
    die Suite ist gruen. Erst die CI klont ein Repo ohne sie und wird rot, mit
    einer Fehlermeldung, die nach einem Aufzeichnungsproblem aussieht statt nach
    einer Regel in `.gitignore`. In `swiss-housing-mcp` ist genau das passiert.
    """
    pfade = [str(FIXTURES / e["name"]) for e in entries]
    try:
        ergebnis = subprocess.run(
            ["git", "check-ignore", *pfade], capture_output=True, text=True, check=False
        )
    except OSError:
        return 0
    ignoriert = [z for z in ergebnis.stdout.splitlines() if z.strip()]
    if ignoriert:
        print("\n!! Diese Aufzeichnungen schliesst .gitignore aus, sie fehlen der CI:")
        for z in ignoriert:
            print(f"     {z}")
        return 1
    return 0


def _write_provenance(recorded_at: str, entries: list[dict[str, Any]]) -> None:
    lines = [
        "# Herkunft der Fixtures",
        "",
        "**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**",
        "",
        f"Aufgezeichnet am **{recorded_at}** vom Endpunkt dieses Servers:",
        f"`{c.ENDPOINT}`.",
        "",
        "Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht",
        "mehr zu unterscheiden — die Datei sieht gleich aus.",
        "",
        "**Ein Endpunkt, sieben Abfrageformen.** Die Form der Antwort haengt hier",
        "an der Abfrage und nicht am Endpunkt: `cube_dimensions` liefert andere",
        "Variablen als `cube_observations`, und ein Stub, der beide gleich raet,",
        "faellt nie auf. Aufgezeichnet ist deshalb eine Antwort je Abfrageform.",
        "",
        "**Aufgezeichnet ist die rohe SPARQL-JSON-Antwort**, nicht das geparste",
        "Ergebnis. `_parse_bindings` gehoert zu dem, was geprueft werden soll; eine",
        "Fixture aus fertigen Zeilen wuerde genau den Parser ueberspringen, den sie",
        "belegen soll.",
        "",
        "**Alle Aufzeichnungen beschreiben denselben Wuerfel.** Der erste Treffer",
        "der Suche bestimmt, welcher — Metadaten, Dimensionen, Beobachtungen und",
        "Codeliste gehoeren damit zusammen und nicht zu sieben verschiedenen",
        "Gegenstaenden. Dasselbe gilt fuer die beiden Gemeinde-Abfragen: sie",
        "treffen dieselbe Gemeinde ueber Name und BFS-Nummer.",
        "",
        "Fehlerpfade — Timeouts, 5xx, eine kaputte Abfrage mit HTTP 400 — bleiben",
        "handgeschrieben. Die lassen sich nicht auf Zuruf aufzeichnen.",
        "",
    ]
    for e in entries:
        lines += [
            f"## `{e['name']}`",
            "",
            f"- **Quelle:** `{e['url'][:160]}`",
            f"- **Aufgezeichnet:** {recorded_at}",
            f"- **Auswahl:** {e['rule']}",
            f"- **Groesse:** {e['bytes']} B ({e['zeilen']} Ergebniszeilen)",
            f"- **SHA-256:** `{e['sha256']}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
