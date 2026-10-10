from __future__ import annotations

import random
import time

from ..engine.visibility import View
from .base import MAFIA_SPEAK, SPEAK, Request


class RandomAgent:
    """Free, deterministic (given a seed) agent for testing the engine."""

    def __init__(self, seed: int | None = None, delay: float = 0.0):
        self.rng = random.Random(seed)
        self.delay = delay  # seconds per action, so a demo game can be watched live

    def act(self, view: View, request: Request) -> str | None:
        if self.delay:
            time.sleep(self.delay)
        if request.kind in (SPEAK, MAFIA_SPEAK):
            return f"I am {view.me}, day {view.day}."
        if request.allow_abstain and self.rng.random() < 0.1:
            return None
        return self.rng.choice(request.options)
