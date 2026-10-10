from __future__ import annotations

import json
from pathlib import Path

from .engine.state import Event


def event_to_dict(ev: Event) -> dict:
    return {**ev.__dict__, "visible_to": None if ev.visible_to is None else sorted(ev.visible_to)}


class JsonlWriter:
    """Append only event log. Flushes every event so a viewer can follow a running game."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("w", encoding="utf-8")

    def write(self, ev: Event) -> None:
        self._f.write(json.dumps(event_to_dict(ev)) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()
