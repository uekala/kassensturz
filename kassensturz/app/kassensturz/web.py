"""Was alle Routen-Module brauchen: Fehler melden, Neuberechnung anstoßen, Zwischenspeicher für Importe."""
from __future__ import annotations

from fastapi import HTTPException

from . import services

# Hochgeladene Dateien zwischen Analyse und Übernahme, je Schlüssel.
_imports: dict[str, dict] = {}


def _err(status: int, text: str):
    raise HTTPException(status_code=status, detail=text)


def _changed() -> None:
    services.schedule_refresh()
