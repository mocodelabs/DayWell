"""Lightweight registries so feature apps can plug into account export without core importing them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Exporter = Callable[[Any], list[dict] | dict]
_exporters: dict[str, Exporter] = {}


def register_export(name: str, fn: Exporter) -> None:
    _exporters[name] = fn


def export_all(user) -> dict[str, Any]:
    return {name: fn(user) for name, fn in sorted(_exporters.items())}


def rows(queryset, *fields: str) -> list[dict]:
    """Serialise a queryset for export with JSON-safe values."""
    out = []
    for row in queryset.values(*fields):
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()})
    return out
