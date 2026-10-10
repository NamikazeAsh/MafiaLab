import random

import pytest

from mafia.agents.scripted import RandomAgent
from mafia.engine import rules
from mafia.engine.game import Game
from mafia.engine.state import GameState, Player, Role
from mafia.engine.visibility import view_for

NAMES = ["Ann", "Bob", "Cy", "Di", "Ed", "Flo", "Gus", "Hal", "Ivy", "Jo"]


def make_game(n=8, seed=0):
    agents = {name: RandomAgent(seed + i) for i, name in enumerate(NAMES[:n])}
    return Game(agents, seed=seed)


@pytest.mark.parametrize("n", range(6, 11))
def test_role_counts_sum(n):
    assert sum(rules.role_counts(n).values()) == n


def test_default_mafia_counts():
    assert {n: rules.role_counts(n)[Role.MAFIA] for n in range(6, 11)} == {6: 1, 7: 2, 8: 2, 9: 2, 10: 3}


def test_mafia_override_and_bounds():
    assert rules.role_counts(6, mafia=2)[Role.MAFIA] == 2
    with pytest.raises(ValueError):
        rules.role_counts(6, mafia=3)
    with pytest.raises(ValueError):
        rules.role_counts(6, mafia=0)


def test_solo_mafia_has_no_chat():
    g = make_game(n=6, seed=1)
    g.run()
    assert len(g.state.mafia_names()) == 1
    assert not [e for e in g.state.events if e.kind in ("mafia_chat", "kill_rule")]


def test_role_counts_bounds():
    with pytest.raises(ValueError):
        rules.role_counts(5)


def test_resolve_night():
    assert rules.resolve_night("A", "A") is None
    assert rules.resolve_night("A", "B") == "A"
    assert rules.resolve_night(None, "B") is None


def test_tally_tie_and_empty():
    assert rules.tally({"a": "x", "b": "y"}) is None
    assert rules.tally({"a": None}) is None
    assert rules.tally({"a": "x", "b": "x", "c": "y"}) == "x"


def test_pick_kill_always_kills_on_tie():
    rng = random.Random(1)
    assert rules.pick_kill({"a": "x", "b": "y"}, rng) in ("x", "y")


def _state(roles):
    return GameState(players={n: Player(n, r) for n, r in roles.items()})


def test_winner():
    s = _state({"a": Role.MAFIA, "b": Role.VILLAGER, "c": Role.VILLAGER})
    assert rules.check_winner(s) is None
    s.players["b"].alive = False
    assert rules.check_winner(s) == "mafia"
    s2 = _state({"a": Role.MAFIA, "b": Role.VILLAGER, "c": Role.VILLAGER})
    s2.players["a"].alive = False
    assert rules.check_winner(s2) == "town"


@pytest.mark.parametrize("seed", range(30))
def test_full_games_finish(seed):
    g = make_game(n=6 + seed % 5, seed=seed)
    assert g.run() in ("town", "mafia")
    assert g.state.events[-1].kind == "end"


def test_deterministic_given_seed():
    a, b = make_game(seed=5), make_game(seed=5)
    a.run(), b.run()
    assert [e.text for e in a.state.events] == [e.text for e in b.state.events]


def test_visibility_no_leaks():
    g = make_game(n=8, seed=3)
    g.run()
    st = g.state
    mafia = set(st.mafia_names())
    for name, p in st.players.items():
        v = view_for(st, name)
        kinds = {e.kind for e in v.events}
        if p.role is not Role.MAFIA:
            assert "mafia_chat" not in kinds and "kill_vote" not in kinds
            assert v.teammates == ()
        else:
            assert set(v.teammates) == mafia - {name}
        if p.role is not Role.DETECTIVE:
            assert "investigate" not in kinds
        if p.role is not Role.DOCTOR:
            assert "save" not in kinds


class Scripted:
    """Mafia kill behavior is configurable; everything else is the first valid option."""

    def __init__(self, kill_pick):
        self.kill_pick = kill_pick

    def act(self, view, request):
        if request.kind in ("speak", "mafia_speak"):
            return "hi"
        if request.kind == "kill":
            return self.kill_pick(view, request)
        return request.options[0]


def _kill_events(g):
    return [e for e in g.state.events if e.kind == "kill_decision"]


def test_mafia_converge_on_one_target():
    def follow(view, request):
        prior = [e for e in view.events if e.kind == "kill_vote" and e.day == view.day]
        if prior:
            return prior[-1].text.rsplit("kill ", 1)[1].rstrip(".")
        return request.options[-1]

    agents = {n: Scripted(follow) for n in NAMES[:8]}
    g = Game(agents, seed=1)
    g.run()
    assert _kill_events(g)
    # every night's decision is one player, and rounds stop as soon as votes match
    assert not [e for e in g.state.events if e.kind == "kill_split"]


def test_mafia_disagreement_still_yields_one_target():
    picks = iter(range(10**6))

    def never_agree(view, request):
        return request.options[next(picks) % len(request.options)]

    agents = {n: Scripted(never_agree) for n in NAMES[:8]}
    g = Game(agents, seed=2)
    g.run()
    assert [e for e in g.state.events if e.kind == "kill_split"]
    assert g.state.events[-1].kind == "end"


def test_setup_event_is_hidden_from_every_player():
    g = make_game(n=7, seed=9)
    g.run()
    setup = [e for e in g.state.events if e.kind == "setup"]
    assert len(setup) == 1 and setup[0].idx == 0
    assert set(setup[0].data["roles"]) == set(NAMES[:7])
    for name in g.state.players:
        assert all(e.kind != "setup" for e in view_for(g.state, name).events)


def test_events_carry_structured_data_for_the_viewer():
    g = make_game(n=8, seed=6)
    g.run()
    by_kind = {}
    for e in g.state.events:
        by_kind.setdefault(e.kind, e)
    assert by_kind["speech"].data["message"] and by_kind["speech"].data["speaker"]
    assert {"voter", "target"} <= set(by_kind["kill_vote"].data)
    assert "target" in by_kind["kill_decision"].data
    assert {"actor", "target"} <= set(by_kind["save"].data)
    assert {"actor", "target", "result"} <= set(by_kind["investigate"].data)
    causes = {e.data["cause"] for e in g.state.events if e.kind == "death"}
    assert causes <= {"night", "vote"} and causes


def test_should_stop_ends_game_early():
    from mafia.engine.errors import GameStopped

    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 10

    agents = {name: RandomAgent(i) for i, name in enumerate(NAMES[:6])}
    g = Game(agents, seed=1, should_stop=stop)
    with pytest.raises(GameStopped):
        g.run()
    assert g.state.events[-1].kind != "end"


def test_abort_game_from_error_hook_propagates():
    from mafia.engine.errors import AbortGame

    class Boom:
        def act(self, view, request):
            raise RuntimeError("api down")

    def on_error(name, request, exc):
        raise AbortGame("stop")

    g = Game({n: Boom() for n in NAMES[:6]}, seed=1, on_error=on_error)
    with pytest.raises(AbortGame):
        g.run()


def test_votes_are_simultaneous():
    seen = []

    class Watcher:
        def act(self, view, request):
            if request.kind == "vote":
                seen.append(sum(1 for e in view.events if e.kind == "vote" and e.day == view.day))
            if request.kind in ("speak", "mafia_speak"):
                return "hi"
            return request.options[0]

    g = Game({n: Watcher() for n in NAMES[:6]}, seed=1)
    g.run()
    assert seen and all(c == 0 for c in seen)


def test_speaking_order_varies():
    firsts = set()
    for seed in range(20):
        g = make_game(n=6, seed=seed)
        g.run()
        speeches = [e for e in g.state.events if e.kind == "speech" and e.day == 1]
        if speeches:
            firsts.add(speeches[0].data["speaker"])
    assert len(firsts) > 2


def test_target_reason_becomes_private_thought():
    class Reasoner:
        def __init__(self):
            self._t = ""

        def pop_thought(self):
            t, self._t = self._t, ""
            return t

        def act(self, view, request):
            if request.kind in ("speak", "mafia_speak"):
                return "hi"
            self._t = "because reasons"
            return request.options[0]

    g = Game({n: Reasoner() for n in NAMES[:6]}, seed=1)
    g.run()
    thoughts = [e for e in g.state.events if e.kind == "thought"]
    assert thoughts and all(e.visible_to == frozenset({e.data["speaker"]}) for e in thoughts)


def test_invalid_agent_falls_back():
    class Bad:
        def act(self, view, request):
            return "nonsense"

    agents = {n: Bad() for n in NAMES[:6]}
    g = Game(agents, seed=1)
    assert g.run() in ("town", "mafia")
    assert g.invalid_actions > 0
