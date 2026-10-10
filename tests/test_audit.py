import json

from mafia.agents.llm_agent import LLMAgent
from mafia.audit import audit_game
from mafia.engine.game import Game

NAMES = ["Ann", "Bob", "Cy", "Di", "Ed", "Flo", "Gus", "Hal"]


class Recorder:
    """A fake model that answers legally and records every prompt, like the real client's trace."""

    def __init__(self):
        self.rows = []

    def chat(self, messages, max_tokens=300, temperature=0.8):
        user = messages[-1]["content"]
        if "Options:" in user:
            first = user.split("Options:")[1].split(".")[0].split(",")[0].strip()
            reply = '{"reason": "r", "target": "%s"}' % first
        else:
            reply = '{"thought": "private reasoning", "say": "I have a thought about this."}'
        self.rows.append({"messages": messages, "response": reply})
        return reply


def play(tmp_path, seed=3):
    rec = Recorder()
    g = Game({n: LLMAgent(rec, persona="plain") for n in NAMES}, seed=seed)
    g.run()
    events = [dict(e.__dict__, visible_to=None if e.visible_to is None else sorted(e.visible_to)) for e in g.state.events]
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(r) for r in rec.rows) + "\n", encoding="utf-8")
    return g, events, rec, trace


def test_a_clean_game_has_no_leaks(tmp_path):
    g, events, rec, trace = play(tmp_path)
    r = audit_game(events, trace)
    assert r["calls"] == len(rec.rows) > 50 and r["history_lines"] > 200
    assert r["leaks"] == [] and r["role_mismatches"] == 0 and r["teammate_mismatches"] == 0


def test_a_mafia_line_in_a_villagers_prompt_is_caught(tmp_path):
    g, events, rec, trace = play(tmp_path)
    mafia_chat = next(e for e in events if e["kind"] == "mafia_chat")
    villager = next(n for n, p in g.state.players.items() if p.role.value == "villager")
    leaked_line = f"[{mafia_chat['phase']} {mafia_chat['day']}] {mafia_chat['text']}"
    for row in rec.rows:  # inject the mafia chat into the first prompt that belongs to the villager
        if f"Your name is {villager}." in row["messages"][0]["content"]:
            row["messages"][-1]["content"] = row["messages"][-1]["content"].replace("Game so far:\n", f"Game so far:\n{leaked_line}\n", 1)
            break
    trace.write_text("\n".join(json.dumps(r) for r in rec.rows) + "\n", encoding="utf-8")
    r = audit_game(events, trace)
    assert len(r["leaks"]) == 1 and r["leaks"][0]["player"] == villager and "[mafia]" in r["leaks"][0]["line"]


def test_another_players_thought_is_caught(tmp_path):
    g, events, rec, trace = play(tmp_path)
    thought = next(e for e in events if e["kind"] == "thought")
    other = next(n for n in NAMES if n != thought["data"]["speaker"])
    line = f"[{thought['phase']} {thought['day']}] {thought['text']}"
    for row in rec.rows:
        if f"Your name is {other}." in row["messages"][0]["content"]:
            row["messages"][-1]["content"] = row["messages"][-1]["content"].replace("Game so far:\n", f"Game so far:\n{line}\n", 1)
            break
    trace.write_text("\n".join(json.dumps(r) for r in rec.rows) + "\n", encoding="utf-8")
    assert [x["player"] for x in audit_game(events, trace)["leaks"]] == [other]


def test_wrong_role_or_teammates_in_the_system_prompt_are_caught(tmp_path):
    g, events, rec, trace = play(tmp_path)
    mafia = next(n for n, p in g.state.players.items() if p.role.value == "mafia")
    for row in rec.rows:
        sys_msg = row["messages"][0]["content"]
        if f"Your name is {mafia}." in sys_msg:
            row["messages"][0]["content"] = sys_msg.replace("You are MAFIA", "You are a VILLAGER", 1)
            break
    trace.write_text("\n".join(json.dumps(r) for r in rec.rows) + "\n", encoding="utf-8")
    assert audit_game(events, trace)["role_mismatches"] == 1


def test_setup_event_is_never_allowed_in_a_prompt(tmp_path):
    g, events, rec, trace = play(tmp_path)
    setup = events[0]
    line = f"[{setup['phase']} {setup['day']}] {setup['text']}"
    rec.rows[0]["messages"][-1]["content"] = rec.rows[0]["messages"][-1]["content"].replace("Game so far:\n", f"Game so far:\n{line}\n", 1)
    trace.write_text("\n".join(json.dumps(r) for r in rec.rows) + "\n", encoding="utf-8")
    assert any("Roles (spectator only)" in x["line"] for x in audit_game(events, trace)["leaks"])
