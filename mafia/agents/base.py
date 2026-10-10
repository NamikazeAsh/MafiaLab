from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..engine.visibility import View

SPEAK = "speak"
MAFIA_SPEAK = "mafia_speak"
KILL = "kill"
SAVE = "save"
INVESTIGATE = "investigate"
VOTE = "vote"


@dataclass(frozen=True)
class Request:
    kind: str
    options: tuple[str, ...] = ()
    allow_abstain: bool = False


class Agent(Protocol):
    def act(self, view: View, request: Request) -> str | None:
        """Return a message for speak requests, or a target name (None = abstain) otherwise."""
        ...
