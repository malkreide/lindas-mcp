"""Die eine Stelle, an der dieses Paket seine Distributions-Metadaten aufloest.

Gelesen aus den Metadaten der *installierten* Distribution, nie von Hand
geschrieben. Ein Literal ist eine zweite Kopie einer Angabe, die der Build
bestimmt, und zweite Kopien driften — `swiss-procurement-mcp` meldete
`0.4.0` an simap.ch, waehrend das Paket auf PyPI bei `0.18.3` stand,
vierzehn Minor-Versionen spaeter, aus genau so einer Konstante.

Dasselbe Argument traegt ueber die Version hinaus: Zusammenfassung und
Projekt-URL stehen in `pyproject.toml` und gehen als `serverInfo` an jeden
Client. Von Hand danebengeschrieben waeren sie dieselbe Drift eine Stelle
weiter, nur ohne Gate, das sie faengt.

Ein eigenes Modul statt einer Aufloesung in `__init__`, damit andere Module
die Angaben importieren koennen, ohne die Paketwurzel zu laden.

Der Versions-Fallback markiert sich selbst als solcher: ein lokales
PEP-440-Segment nach `+` kann nie mit einem Release verwechselt werden, anders
als ein plausibel aussehendes `0.0.0`. Fuer Zusammenfassung und URL gibt es
keinen ehrlichen Ersatzwert — dort ist `None` die Antwort, und beide Felder
sind im `Implementation`-Objekt der Spec optional.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import metadata as _pkg_metadata
from importlib.metadata import version as _pkg_version

DISTRIBUTION = "lindas-mcp"

try:
    __version__ = _pkg_version(DISTRIBUTION)
except PackageNotFoundError:  # Quellbaum statt Installation
    __version__ = "0.0.0+source"


def _read_metadata() -> tuple[str | None, str | None]:
    """(Summary, Homepage) aus den Paket-Metadaten, oder (None, None).

    `Home-page` ist das alte Core-Metadata-Feld; hatchling schreibt statt
    dessen `Project-URL: Homepage, <url>`. Beide Schreibweisen werden gelesen,
    sonst haengt das Ergebnis am Build-Backend statt am Projekt.
    """
    try:
        meta = _pkg_metadata(DISTRIBUTION)
    except PackageNotFoundError:
        return None, None
    homepage = meta.get("Home-page")
    if not homepage:
        for entry in meta.get_all("Project-URL") or ():
            label, _, url = entry.partition(",")
            if label.strip().lower() == "homepage":
                homepage = url.strip()
                break
    return meta.get("Summary") or None, homepage or None


__summary__, __homepage__ = _read_metadata()

__all__ = ["DISTRIBUTION", "__homepage__", "__summary__", "__version__"]
