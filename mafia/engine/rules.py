from __future__ import annotations

import random
from collections import Counter

from .state import GameState, Role


def default_mafia(n: int) -> int:
    """6 players get 1 mafia (2 hits parity too fast), 7 to 9 get 2, 10 gets 3."""
    return max(1, (n - 1) // 3)


def role_counts(n: int, mafia: int | None = None) -> dict[Role, int]:
    if not 6 <= n <= 10:
        raise ValueError("classic core supports 6 to 10 players")
    mafia = default_mafia(n) if mafia is None else mafia
    if not 1 <= mafia <= (n - 2) // 2:
        raise ValueError("invalid mafia count for this player total")
    return {
        Role.MAFIA: mafia,
        Role.DOCTOR: 1,
        Role.DETECTIVE: 1,
        Role.VILLAGER: n - mafia - 2,
    }


def assign_roles(names: list[str], rng: random.Random, mafia: int | None = None) -> dict[str, Role]:
    roles: list[Role] = []
    for role, count in role_counts(len(names), mafia).items():
        roles.extend([role] * count)
    rng.shuffle(roles)
    return dict(zip(names, roles))


def check_winner(state: GameState) -> str | None:
    mafia = len(state.alive_with_role(Role.MAFIA))
    town = len(state.alive()) - mafia
    if mafia == 0:
        return "town"
    if mafia >= town:
        return "mafia"
    return None


def resolve_night(kill: str | None, save: str | None) -> str | None:
    """Return the name of the victim, or None if nobody dies."""
    if kill is None or kill == save:
        return None
    return kill


def tally(votes: dict[str, str | None], rng: random.Random | None = None) -> str | None:
    """Strict plurality. A tie or no votes means no elimination."""
    counts = Counter(v for v in votes.values() if v is not None)
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def pick_kill(votes: dict[str, str | None], rng: random.Random) -> str | None:
    """Mafia kill: plurality, ties broken randomly (a kill always happens if anyone voted)."""
    counts = Counter(v for v in votes.values() if v is not None)
    if not counts:
        return None
    top = max(counts.values())
    leaders = sorted(t for t, c in counts.items() if c == top)
    return rng.choice(leaders)
