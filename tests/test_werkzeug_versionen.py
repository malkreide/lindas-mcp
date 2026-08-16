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

# Formen, in denen ein Schritt ein Paket eigenstaendig installiert. Die erste
# Fassung dieses Tests kannte nur `pip install ruff` und liess damit
# `pip install --upgrade ruff==…`, `pip install "ruff==…"`, `pip3 install`,
# `uv tool install` und `uv run --with ruff==…` durch — allesamt Formen, die
# den Pin genauso ueberstimmen. Aufgefallen ist das in einem Codex-Review.
_INSTALL_FORM = re.compile(
    r"(?:pip3?\s+install|python\s+-m\s+pip\s+install|uv\s+pip\s+install"
    r"|uv\s+tool\s+install|uv\s+add|pipx\s+install|--with)\b"
)
# ruff als eigenes Paket-Argument. Anfuehrungszeichen sind erlaubt, ein
# vorangehendes Wort-, Pfad- oder Bindestrich-Zeichen nicht: sonst zaehlten
# `ruff-lsp` und `scripts/ruff_helper.py` mit.
_RUFF_PAKET = re.compile(r"""(?<![\w./-])["']?ruff(?![\w-])""")


def _installiert_ruff(zeile: str) -> bool:
    """Installiert diese Zeile ruff als benanntes Paket?

    `pip install -e ".[dev]"` zieht ruff ebenfalls herein — das ist aber der
    richtige Weg und darf nicht anschlagen. Entscheidend ist deshalb, ob nach
    dem Install-Befehl ein eigenes Argument `ruff` steht.
    """
    treffer = _INSTALL_FORM.search(zeile)
    return bool(treffer) and bool(_RUFF_PAKET.search(zeile[treffer.end() :]))


def _workflow_dateien() -> list[pathlib.Path]:
    """Beide Endungen: GitHub laedt `*.yml` UND `*.yaml`."""
    return sorted([*_WORKFLOWS.glob("*.yml"), *_WORKFLOWS.glob("*.yaml")])


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
    for workflow in _workflow_dateien():
        treffer = [z for z in _ohne_kommentare(workflow) if _installiert_ruff(z)]
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
    workflows = _workflow_dateien()
    assert len(workflows) >= 2, f"Workflow-Scan findet fast nichts: {workflows}"
    assert any("ruff check" in w.read_text() for w in workflows), (
        "kein Workflow ruft ruff auf — der Scan sucht am falschen Ort"
    )


def test_unter_scripts_liegt_ueberhaupt_python() -> None:
    """Sonde: Ohne Dateien dort waere die Umfang-Forderung oben folgenlos."""
    skripte = sorted((_ROOT / "scripts").glob("*.py"))
    assert skripte, "keine Python-Dateien unter scripts/ — dann prueft der Umfang dort nichts"


def test_der_erkenner_kennt_die_gaengigen_installationsformen() -> None:
    """Der Scan ist nur so gut wie das, was er als Install erkennt.

    Ohne diese Tabelle ist die Zusicherung oben gruen, weil sie die Form nicht
    kennt — nicht, weil sie fehlt. Genau so war es: Die erste Fassung suchte
    woertlich nach `pip install ruff` und uebersah fuenf von sieben geprueften
    Schreibweisen.
    """
    muss_treffen = [
        "run: pip install ruff==0.16.1",
        "run: pip install --upgrade ruff==0.16.1",
        'run: pip install "ruff==0.16.1"',
        "run: pip install 'ruff==0.16.1'",
        "run: pip3 install ruff==0.16.1",
        "run: python -m pip install ruff==0.16.1",
        "run: uv pip install ruff==0.16.1 --system",
        "run: uv tool install ruff==0.16.1",
        "run: uv add ruff==0.16.1",
        "run: pipx install ruff==0.16.1",
        "run: uv run --with ruff==0.16.1 ruff check src/",
        "run: pip install ruff",
        "run: pip install pytest ruff==0.16.1",
        "run: pip install ruff[extra]==0.16.1",
    ]
    darf_nicht_treffen = [
        'run: pip install -e ".[dev]"',
        'run: uv pip install -e ".[dev]" --system',
        "run: ruff check src/ tests/ scripts/",
        "run: ruff format --check src/ tests/",
        "run: pip install ruff-lsp",
        "run: pip install uv",
        "run: python -m pip install --upgrade pip",
        "run: pip install build hatchling",
        "run: uv run --with pip-audit pip-audit",
        "run: python scripts/ruff_helper.py",
        "run: pip install -r requirements.txt",
        "name: Lint mit ruff",
    ]
    uebersehen = [z for z in muss_treffen if not _installiert_ruff(z)]
    assert not uebersehen, f"Erkenner uebersieht: {uebersehen}"
    fehlalarm = [z for z in darf_nicht_treffen if _installiert_ruff(z)]
    assert not fehlalarm, f"Erkenner schlaegt faelschlich an: {fehlalarm}"
