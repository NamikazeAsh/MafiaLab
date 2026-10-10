from mafia.agents.base import KILL, SPEAK, VOTE, Request
from mafia.agents.llm_agent import INVALID, LLMAgent, clean_speech, parse_target
from mafia.engine.game import Game
from mafia.engine.state import Role
from mafia.engine.visibility import view_for

NAMES = ["Ann", "Bob", "Cy", "Di", "Ed", "Flo"]


class FakeClient:
    """Answers speech with text and target requests with the first listed option."""

    def __init__(self):
        self.prompts = []

    def chat(self, messages, max_tokens=300, temperature=0.8):
        self.prompts.append(messages)
        user = messages[-1]["content"]
        if "Options:" in user:
            opts = user.split("Options:")[1].split(".")[0].split(",")
            return '{"reason": "x", "target": "%s"}' % opts[0].strip()
        return "Ann: I think we should be careful."


def test_parse_target_json_and_fallback():
    req = Request(VOTE, ("Bob", "Cy"), allow_abstain=True)
    assert parse_target('{"target": "bob"}', req) == "Bob"
    assert parse_target('{"target": null}', req) is None
    assert parse_target("I vote Cy for sure", req) == "Cy"
    assert parse_target("Bob or Cy", req) is INVALID
    assert parse_target("no idea", req) is INVALID
    assert parse_target('{"target": "Zed"}', Request(KILL, ("Bob",))) is INVALID


def _view(me="Cy", day=1, n_events=0):
    from mafia.engine.state import Event
    from mafia.engine.visibility import View

    events = tuple(Event(i, day, "night", "speech", "x") for i in range(n_events))
    return View(me, Role.VILLAGER, day, "night", ("Ann", "Bob", "Cy", "Di", "Ed", "Flo"), (), (), events)


def _options_in_prompt(prompt: str) -> list[str]:
    return [n.strip() for n in prompt.split("Options:")[1].split(".")[0].split(",")]


def test_option_order_varies_but_is_complete_and_reproducible():
    from mafia.agents.llm_agent import build_request

    req = Request(VOTE, ("Ann", "Bob", "Di", "Ed", "Flo"), allow_abstain=True)
    first = [_options_in_prompt(build_request(_view(n_events=n), req))[0] for n in range(60)]
    assert sorted(_options_in_prompt(build_request(_view(), req))) == sorted(req.options)
    assert build_request(_view(n_events=7), req) == build_request(_view(n_events=7), req)  # reproducible
    # No name is always first, and none dominates (a fixed order would give one name 100%).
    assert len(set(first)) == 5 and max(first.count(n) for n in set(first)) <= 30


def test_alive_list_is_shuffled_too_and_parsing_ignores_order():
    from mafia.agents.llm_agent import build_request

    req = Request(KILL, ("Bob", "Di"))
    orders = {build_request(_view(n_events=n), req).split("Alive: ")[1].split(".")[0] for n in range(40)}
    assert len(orders) > 5
    assert parse_target('{"target": "Di"}', req) == "Di"


def test_clean_speech():
    assert clean_speech('Ann: "hello"', "Ann") == "hello"


def test_clean_speech_strips_leaked_tags():
    assert clean_speech("[night 2] [mafia] Di: lock it in", "Di") == "lock it in"


def test_parse_speech_variants():
    from mafia.agents.llm_agent import parse_speech

    assert parse_speech('{"thought": "t", "say": "hi"}', "Ann") == ("t", "hi")
    assert parse_speech('```json\n{"thought": "t", "say": "Ann: hi"}\n```', "Ann") == ("t", "hi")
    assert parse_speech("just plain words", "Ann") == ("", "just plain words")


def test_thoughts_are_private():
    class ThinkClient(FakeClient):
        def chat(self, messages, max_tokens=300, temperature=0.8):
            out = super().chat(messages, max_tokens, temperature)
            if "Options:" in messages[-1]["content"]:
                return out
            return '{"thought": "SECRETTHOUGHT", "say": "hello all"}'

    client = ThinkClient()
    g = Game({n: LLMAgent(client) for n in NAMES}, seed=4)
    g.run()
    thoughts = [e for e in g.state.events if e.kind == "thought"]
    assert thoughts
    for e in thoughts:
        speaker = e.data["speaker"]
        assert e.visible_to == frozenset({speaker})
    for msgs in client.prompts:
        text = " ".join(m["content"] for m in msgs)
        me = text.split("Your name is ")[1].split(".")[0]
        # a player may only ever see their own thoughts, never someone else's
        for line in text.splitlines():
            if "(thinks)" in line:
                assert f"(thinks) {me}:" in line


def test_full_game_with_fake_llm():
    client = FakeClient()
    agents = {n: LLMAgent(client) for n in NAMES}
    g = Game(agents, seed=2)
    assert g.run() in ("town", "mafia")
    assert g.invalid_actions == 0


def test_prompts_do_not_leak_hidden_info():
    client = FakeClient()
    agents = {n: LLMAgent(client) for n in NAMES}
    g = Game(agents, seed=2)
    g.run()
    st = g.state
    mafia = set(st.mafia_names())
    for msgs in client.prompts:
        text = " ".join(m["content"] for m in msgs)
        me = text.split("Your name is ")[1].split(".")[0]
        if st.players[me].role is not Role.MAFIA:
            assert "[mafia]" not in text
            assert "fellow mafia" not in text
            assert "You are MAFIA" not in text
