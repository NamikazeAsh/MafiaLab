from __future__ import annotations

from dataclasses import dataclass

from .state import Event, GameState, Role


@dataclass(frozen=True)
class View:
    """Everything one player is allowed to know. Agents only ever receive this."""

    me: str
    role: Role
    day: int
    phase: str
    alive: tuple[str, ...]
    dead: tuple[str, ...]
    teammates: tuple[str, ...]
    events: tuple[Event, ...]


def view_for(state: GameState, name: str) -> View:
    me = state.players[name]
    teammates = tuple(
        n for n in state.mafia_names() if n != name
    ) if me.role is Role.MAFIA else ()
    events = tuple(
        e for e in state.events if e.visible_to is None or name in e.visible_to
    )
    return View(
        me=name,
        role=me.role,
        day=state.day,
        phase=state.phase.value,
        alive=tuple(state.alive()),
        dead=tuple(n for n, p in state.players.items() if not p.alive),
        teammates=teammates,
        events=events,
    )
