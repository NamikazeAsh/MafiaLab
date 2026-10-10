from __future__ import annotations

import os
import random
import time
from pathlib import Path

from .agents.llm_agent import PERSONAS, LLMAgent
from .agents.scripted import RandomAgent
from .llm.client import ChatClient

ROOT = Path(__file__).resolve().parent.parent
# Seat order. Games with 9 or 10 players use the last two names.
NAMES = ["Ay", "Bee", "Cee", "Dee", "Ey", "Foo", "Gi", "Himothy", "Ivy", "Jojo"]
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class SetupError(Exception):
    """A problem the user can fix, such as a missing API key."""


def load_env(path: str = ".env") -> None:
    """Minimal .env loader. Real environment variables win over the file."""
    p = ROOT / path
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def build_agents(
    names: list[str],
    *,
    use_random: bool = False,
    model: str = DEFAULT_MODEL,
    rpm: float = 10,
    seed: int | None = None,
    log_dir: str | Path = "logs",
    delay: float = 0.0,
    cache: bool = True,
) -> tuple[dict, ChatClient | None]:
    """Create one agent per name. Returns (agents, client) where client is None for random agents.

    The cache replays identical prompts, which is what lets an interrupted batch resume. Turn it off
    (cache=False) for replicates, otherwise rerunning the same seeds just replays the earlier replies.
    """
    if use_random:
        return {n: RandomAgent(i, delay=delay) for i, n in enumerate(names)}, None
    Path(log_dir).mkdir(exist_ok=True)
    client = ChatClient(
        model=model, rpm=rpm, cache_dir=".cache/llm" if cache else None,
        trace_path=Path(log_dir) / f"trace_{int(time.time())}.jsonl",
    )
    if not client.api_key:
        raise SetupError("Set GEMINI_API_KEY first (free key from aistudio.google.com).")
    personas = PERSONAS[:]
    random.Random(seed).shuffle(personas)
    return {n: LLMAgent(client, persona=personas[i]) for i, n in enumerate(names)}, client
