"""ASGI entrypoint: ``uvicorn app.main:app``."""

from __future__ import annotations

from .api import create_app
from .bootstrap import build

_settings, _engine, _session_factory, queue, registry = build()

app = create_app(queue, registry)
