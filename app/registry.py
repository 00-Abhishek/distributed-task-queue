"""Job handler registry and the built-in example handlers."""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional


class HandlerRegistry:
    """Maps a job ``type`` to the callable that executes it."""

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable] = {}

    def register(self, name: str):
        def decorator(func: Callable) -> Callable:
            self._handlers[name] = func
            return func

        return decorator

    def get(self, name: str) -> Optional[Callable]:
        return self._handlers.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._handlers

    def names(self) -> list:
        return sorted(self._handlers)


def register_default_handlers(registry: HandlerRegistry) -> HandlerRegistry:
    """Register a few demo handlers so the queue is usable out of the box."""

    @registry.register("echo")
    def echo(payload: dict) -> dict:
        return {"echo": payload}

    @registry.register("add")
    def add(payload: dict) -> dict:
        return {"sum": int(payload.get("a", 0)) + int(payload.get("b", 0))}

    @registry.register("sleep")
    def sleep(payload: dict) -> dict:
        seconds = min(float(payload.get("seconds", 1)), 30)
        time.sleep(seconds)
        return {"slept": seconds}

    return registry
