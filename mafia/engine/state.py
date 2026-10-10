from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    VILLAGER = "villager"
    MAFIA = "mafia"
    DOCTOR = "doctor"
    DETECTIVE = "detective"

    @property
    def team(self) -> str:
        return "mafia" if self is Role.MAFIA else "town"


class Phase(str, Enum):
    NIGHT = "night"
    DAY = "day"
    OVER = "over"


@dataclass
class Player:
    name: str
    role: Role
    alive: bool = True


@dataclass(frozen=True)
class Event:
    """One thing that happened. visible_to None means public."""

    idx: int
    day: int
    phase: str
    kind: str
    text: str
    data: dict = field(default_factory=dict)
    visible_to: frozenset[str] | None = None


@dataclass
class GameState:
    players: dict[str, Player]
    day: int = 0
    phase: Phase = Phase.NIGHT
    events: list[Event] = field(default_factory=list)
    winner: str | None = None

    def alive(self) -> list[str]:
        return [n for n, p in self.players.items() if p.alive]

    def alive_with_role(self, role: Role) -> list[str]:
        return [n for n, p in self.players.items() if p.alive and p.role is role]

    def mafia_names(self) -> list[str]:
        return [n for n, p in self.players.items() if p.role is Role.MAFIA]

    def emit(
        self,
        kind: str,
        text: str,
        data: dict | None = None,
        visible_to: set[str] | frozenset[str] | None = None,
    ) -> Event:
        ev = Event(
            idx=len(self.events),
            day=self.day,
            phase=self.phase.value,
            kind=kind,
            text=text,
            data=data or {},
            visible_to=None if visible_to is None else frozenset(visible_to),
        )
        self.events.append(ev)
        return ev
