from __future__ import annotations

import random
from typing import Callable

from ..agents.base import (
    INVESTIGATE,
    KILL,
    MAFIA_SPEAK,
    SAVE,
    SPEAK,
    VOTE,
    Agent,
    Request,
)
from . import rules
from .errors import GameStopped
from .state import GameState, Phase, Player, Role
from .visibility import view_for

MAX_RETRIES = 2
_ERROR = object()


class Game:
    def __init__(
        self,
        agents: dict[str, Agent],
        seed: int | None = None,
        discussion_rounds: int = 2,
        mafia_chat_rounds: int = 1,
        mafia_kill_rounds: int = 3,
        mafia_count: int | None = None,
        on_event: Callable | None = None,
        on_error: Callable | None = None,
        should_stop: Callable[[], bool] | None = None,
        meta: dict | None = None,
    ):
        self.on_error = on_error
        self.should_stop = should_stop
        self.meta = meta or {}
        self.seed = seed
        self.last_error = ""
        self.agents = agents
        self.rng = random.Random(seed)
        self.discussion_rounds = discussion_rounds
        self.mafia_chat_rounds = mafia_chat_rounds
        self.mafia_kill_rounds = mafia_kill_rounds
        self.on_event = on_event
        names = list(agents)
        roles = rules.assign_roles(names, self.rng, mafia_count)
        self.state = GameState(players={n: Player(n, roles[n]) for n in names})
        self.invalid_actions = 0

    # ---- plumbing -------------------------------------------------------
    def _emit(self, *args, **kwargs):
        ev = self.state.emit(*args, **kwargs)
        if self.on_event:
            self.on_event(ev)
        return ev

    def _emit_thought(self, name: str):
        """Log an agent's private reasoning. Only that player can see it; it is never shared."""
        pop = getattr(self.agents[name], "pop_thought", None)
        thought = pop() if pop else ""
        if thought:
            self._emit("thought", f"(thinks) {name}: {thought}", {"speaker": name, "thought": thought}, {name})

    def _ask(self, name: str, request: Request) -> str | None:
        """Ask an agent, validate, retry, then fall back to a safe default."""
        is_speech = request.kind in (SPEAK, MAFIA_SPEAK)
        if self.should_stop and self.should_stop():
            raise GameStopped()
        for _ in range(MAX_RETRIES + 1):
            try:
                result = self.agents[name].act(view_for(self.state, name), request)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                if self.on_error:
                    self.on_error(name, request, e)
                result = _ERROR
            if result is _ERROR:
                self.invalid_actions += 1
                continue
            if is_speech:
                if isinstance(result, str) and result.strip():
                    self._emit_thought(name)
                    return result.strip()
            elif result is None and request.allow_abstain:
                self._emit_thought(name)
                return None
            elif result in request.options:
                self._emit_thought(name)
                return result
            self.invalid_actions += 1
        if is_speech:
            return "(says nothing)"
        if request.allow_abstain:
            return None
        return self.rng.choice(request.options)

    # ---- phases ---------------------------------------------------------
    def _night(self) -> str | None:
        st = self.state
        st.phase = Phase.NIGHT
        st.day += 1
        self._emit("phase", f"Night {st.day} falls.")
        alive = st.alive()

        mafia = st.alive_with_role(Role.MAFIA)
        audience = set(mafia)
        chat_rounds = self.mafia_chat_rounds if len(mafia) > 1 else 0
        for _ in range(chat_rounds):
            for m in mafia:
                msg = self._ask(m, Request(MAFIA_SPEAK))
                self._emit("mafia_chat", f"[mafia] {m}: {msg}", {"speaker": m, "message": msg}, audience)
        targets = tuple(n for n in alive if st.players[n].role is not Role.MAFIA)
        if len(mafia) > 1:
            self._emit("kill_rule", "[mafia] The mafia must agree on ONE target to kill.", {}, audience)
        kill_votes: dict[str, str | None] = {}
        for rnd in range(1, self.mafia_kill_rounds + 1):
            kill_votes = {}
            for m in mafia:
                kill_votes[m] = self._ask(m, Request(KILL, targets))
                self._emit(
                    "kill_vote",
                    f"[mafia] {m} votes to kill {kill_votes[m]}.",
                    {"voter": m, "target": kill_votes[m]},
                    audience,
                )
            if len(set(kill_votes.values())) == 1:
                break
            if rnd < self.mafia_kill_rounds:
                self._emit("kill_split", "[mafia] You disagree. Vote again and agree on one target.", {}, audience)
        kill = rules.pick_kill(kill_votes, self.rng)
        if kill:
            self._emit("kill_decision", f"[mafia] The mafia will kill {kill}.", {"target": kill}, audience)

        save = None
        for d in st.alive_with_role(Role.DOCTOR):
            save = self._ask(d, Request(SAVE, tuple(alive)))
            self._emit("save", f"You protect {save}.", {"actor": d, "target": save}, {d})

        for det in st.alive_with_role(Role.DETECTIVE):
            targets = tuple(n for n in alive if n != det)
            t = self._ask(det, Request(INVESTIGATE, targets))
            res = "MAFIA" if st.players[t].role is Role.MAFIA else "not mafia"
            self._emit(
                "investigate",
                f"You investigate {t}: {res}.",
                {"actor": det, "target": t, "result": res},
                {det},
            )

        return rules.resolve_night(kill, save)

    def _kill(self, victim: str, how: str, cause: str):
        p = self.state.players[victim]
        p.alive = False
        self._emit(
            "death",
            f"{victim} {how}. They were {p.role.value}.",
            {"victim": victim, "role": p.role.value, "cause": cause},
        )

    def _day(self, victim: str | None):
        st = self.state
        st.phase = Phase.DAY
        self._emit("phase", f"Day {st.day} begins.")
        if victim:
            self._kill(victim, "was killed in the night", cause="night")
        else:
            self._emit("no_death", "Nobody died last night.")
        if rules.check_winner(st):
            return

        # Speaking order is shuffled each day so nobody is always first or last.
        order = st.alive()
        self.rng.shuffle(order)
        for _ in range(self.discussion_rounds):
            for n in order:
                msg = self._ask(n, Request(SPEAK))
                self._emit("speech", f"{n}: {msg}", {"speaker": n, "message": msg})

        # Votes are secret until everyone has voted, so nobody can bandwagon on earlier votes.
        votes = {}
        for n in order:
            options = tuple(x for x in st.alive() if x != n)
            votes[n] = self._ask(n, Request(VOTE, options, allow_abstain=True))
        for n, target in votes.items():
            self._emit("vote", f"{n} votes for {target or 'nobody'}.", {"voter": n, "target": target})
        out = rules.tally(votes)
        if out:
            self._kill(out, "was voted out", cause="vote")
        else:
            self._emit("no_lynch", "The vote was tied or empty. Nobody is eliminated.")

    # ---- main loop ------------------------------------------------------
    def run(self) -> str:
        st = self.state
        roster = ", ".join(st.players)
        roles = {n: p.role.value for n, p in st.players.items()}
        personas = {n: getattr(a, "persona", "") for n, a in self.agents.items()}
        # visible_to is an empty set: spectators and logs see it, no agent ever does.
        self._emit(
            "setup",
            f"Roles (spectator only): {roles}",
            {
                "players": list(st.players),
                "roles": roles,
                "personas": personas,
                "mafia_count": sum(1 for r in roles.values() if r == "mafia"),
                "seed": self.seed,
                **self.meta,
            },
            visible_to=set(),
        )
        self._emit("start", f"Game start. Players: {roster}.")
        while True:
            self._day(self._night())
            winner = rules.check_winner(st)
            if winner:
                break
        st.winner = winner
        st.phase = Phase.OVER
        reveal = {n: p.role.value for n, p in st.players.items()}
        self._emit("end", f"{winner} wins.", {"winner": winner, "roles": reveal})
        return winner
