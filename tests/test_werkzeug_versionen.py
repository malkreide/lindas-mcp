"""Die ruff-Version steht an genau einer Stelle, und beide Gates reichen gleich weit.

Der Pin ist hier bereits die einzige Quelle: `ruff==0.16.1` im `[dev]`-Extra,
kein Workflow nennt eine zweite. Dieser Test haelt diesen Zustand, statt ihn
zu behaupten. Der Rueckfall waere still — ein `pip install ruff==<version>`
in einem Workflow liefe nach dem dev-Install und gewaenne gegen pyproject:
Wer den Pin dort anhebt, veraenderte die CI nicht. Kein Gate wird davon rot,
die beiden Laeufe sind sich nur ueber die Regeln uneinig.

Dazu der Umfang. `ruff check` und `ruff format --check` liefen ueber
`src/ tests/`, waehrend unter `scripts/` zwei Python-Dateien liegen — darunter
`classify_live_run.py`, das entscheidet, ob ein roter Live-Lauf ein Issue
aufmacht. Beide Gates sahen sie nie. Zwei Gates mit zwei Reichweiten sehen aus
wie ein Gate.

Bewusst ohne `tomllib`: Die CI faehrt hier auch Python 3.10, und dort gibt es
das Modul noch nicht. Ein Test, der auf einer Matrix-Zeile mit
ModuleNotFoundError abbricht, prueft dort gar nichts.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"

# Eine ruff-Angabe in einer Abhaengigkeitsliste: `"ruff==0.16.1"`,
# `"ruff>=0.4.0"`, `"ruff"`. Die Anfuehrungszeichen im Muster halten die
# Sektion `[tool.ruff]` heraus; nach `ruff` darf nur ein Vergleichsoperator
# oder das schliessende Zeichen folgen, sonst zaehlte `"ruff-lsp"` mit.
_RUFF_SPEC = re.compile(r"""["']ruff((?:[<>=!~][^"']*)?)["']""")


def _ruff_angaben() -> list[str]:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return [m.group(0).strip("\"'") for m in _RUFF_SPEC.finditer(text)]


def _ohne_kommentare(pfad: pathlib.Path) -> list[str]:
    """Zeilen ohne YAML-Kommentare — sonst loest ein erklaerender Hinweis den Test aus."""
    return [
        z.strip()
        for z in pfad.read_text(encoding="utf-8").splitlines()
        if not z.lstrip().startswith("#")
    ]


def test_ruff_ist_exakt_gepinnt() -> None:
    """Eine Spanne laesst lokalen Lauf und CI verschiedene Versionen fahren."""
    angaben = _ruff_angaben()
    assert len(angaben) == 1, f"genau eine ruff-Angabe erwartet, gefunden: {angaben}"
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", angaben[0]), (
        f"ruff muss als ruff==X.Y.Z gepinnt sein, gefunden {angaben[0]!r}."
    )


def test_der_pin_ist_die_einzige_versionsquelle() -> None:
    """Kein Workflow darf ruff selbst installieren."""
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        treffer = [z for z in _ohne_kommentare(workflow) if re.search(r"pip install\s+ruff", z)]
        assert not treffer, (
            f"{workflow.name} installiert ruff direkt ({treffer}). Dieser Schritt "
            "laeuft nach dem dev-Install und ueberstimmt den Pin in pyproject."
        )


def test_beide_ruff_gates_haben_denselben_umfang() -> None:
    """Ein Verzeichnis, das nur eines der beiden Gates sieht, ist ungeprueft."""
    zeilen = _ohne_kommentare(_WORKFLOWS / "ci.yml")
    check = [z for z in zeilen if "ruff check" in z]
    formatieren = [z for z in zeilen if "ruff format" in z]
    assert len(check) == 1 and len(formatieren) == 1, (
        f"je genau einen Aufruf erwartet, gefunden check={check} format={formatieren}"
    )
    umfang_check = check[0].split("ruff check", 1)[1].split()
    umfang_format = [t for t in formatieren[0].split("ruff format", 1)[1].split() if t != "--check"]
    assert umfang_check == umfang_format, (
        f"ruff check prueft {umfang_check}, ruff format prueft {umfang_format} — "
        "ein Verzeichnis faellt damit aus einem der beiden Gates."
    )
    assert "scripts/" in umfang_check, (
        f"`scripts/` fehlt im Gate-Umfang ({umfang_check}); die Skripte dort "
        "werden dann von ruff nie gesehen."
    )


def test_der_workflow_scan_findet_ueberhaupt_etwas() -> None:
    """Sichert die Pruefungen oben gegen ein leeres Verzeichnis ab."""
    workflows = list(_WORKFLOWS.glob("*.yml"))
    assert len(workflows) >= 2, f"Workflow-Scan findet fast nichts: {workflows}"
    assert any("ruff check" in w.read_text() for w in workflows), (
        "kein Workflow ruft ruff auf — der Scan sucht am falschen Ort"
    )


def test_unter_scripts_liegt_ueberhaupt_python() -> None:
    """Sonde: Ohne Dateien dort waere die Umfang-Forderung oben folgenlos."""
    skripte = sorted((_ROOT / "scripts").glob("*.py"))
    assert skripte, "keine Python-Dateien unter scripts/ — dann prueft der Umfang dort nichts"
