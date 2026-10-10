import json

import pytest

from mafia.analysis import load_events
from mafia.judge import build_casebook, judge_batch, judge_game, parse_judgement, summarize_judgements

ROLES = {"Ann": "mafia", "Bob": "detective", "Cy": "doctor", "Di": "villager", "Ed": "villager", "Flo": "villager"}


def ev(kind, day=1, phase="day", text="", **data):
    return {"idx": 0, "day": day, "phase": phase, "kind": kind, "text": text, "data": data, "visible_to": None}


def small_game():
    return [
        ev("setup", 0, "night", roles=ROLES, players=list(ROLES)),
        ev("phase", 1, "night"),
        ev("thought", 1, "night", speaker="Ann", thought="Kill Di early."),
        ev("kill_decision", 1, "night", target="Di"),
        ev("thought", 1, "night", speaker="Cy", thought="Protect Di, random."),
        ev("save", 1, "night", actor="Cy", target="Di"),
        ev("thought", 1, "night", speaker="Bob", thought="Check Ann."),
        ev("investigate", 1, "night", actor="Bob", target="Ann", result="MAFIA"),
        ev("phase", 1, "day"),
        ev("no_death", 1),
        ev("speech", 1, speaker="Ed", message="Nobody died, interesting."),
        ev("thought", 1, speaker="Cy", thought="Di seems quiet."),
        ev("vote", 1, voter="Cy", target="Di"),
        ev("vote", 1, voter="Bob", target="Ann"),
        ev("vote", 1, voter="Ed", target=None),
        ev("death", 1, victim="Ann", role="mafia", cause="vote"),
        ev("end", 1, winner="town", roles=ROLES),
    ]


def test_casebook_lists_every_decision_with_the_players_private_knowledge():
    text, decisions = build_casebook(small_game())
    assert [(d["id"], d["kind"], d["player"]) for d in decisions] == [
        ("D1", "mafia kill", "Ann"), ("D2", "protect", "Cy"), ("D3", "check", "Bob"), ("D4", "vote", "Cy"), ("D5", "vote", "Bob")]
    assert "Ann (mafia), Bob (detective)" in text                               # the judge sees every role
    assert "Cy's private reasoning: Di seems quiet." in text
    assert "their protections: night 1: protected Di (nobody died that night)" in text   # what the doctor knows when voting
    assert "their checks: Ann is MAFIA" in text                                 # what the detective knows when voting
    assert "Ed abstains" in text and "Cy (doctor) protects Di." in text
    assert "Ann was voted out. They were mafia." in text and "GAME OVER: town wins." in text


def test_parse_accepts_fenced_json_and_ignores_unknown_ids_and_verdicts():
    _, decisions = build_casebook(small_game())
    reply = '```json\n{"decisions": [{"id": "D4", "verdict": "illogical", "tag": "ignored_private_knowledge", "why": "Ignored its own save."},' \
            '{"id": "D5", "verdict": "sound", "tag": "weird", "why": "ok"}, {"id": "D99", "verdict": "sound", "tag": "reasonable", "why": "x"},' \
            '{"id": "D1", "verdict": "maybe", "tag": "reasonable", "why": "x"}], "game": {"overall": 3, "summary": "Fine."}}\n```'
    p = parse_judgement(reply, decisions)
    assert [(r["id"], r["verdict"], r["tag"]) for r in p["decisions"]] == [("D4", "illogical", "ignored_private_knowledge"), ("D5", "sound", "other")]
    assert p["overall"] == 3
    assert parse_judgement("no json here", decisions) is None
    assert parse_judgement('{"decisions": []}', decisions) is None


class Judge:
    """A scripted judge: marks the doctor's vote as illogical and everything else sound."""

    model = "fake-judge"

    def __init__(self, bad_first=False):
        self.calls = 0
        self.bad_first = bad_first

    def chat(self, messages, max_tokens=300, temperature=0.8):
        self.calls += 1
        if self.bad_first and self.calls == 1:
            return "I cannot answer that."
        text = messages[-1]["content"]
        ids = [line.split("]")[0][1:] for line in text.splitlines() if line.startswith("[D")]
        rows = []
        for line in text.splitlines():
            if line.startswith("[D"):
                did = line.split("]")[0][1:]
                bad = "Cy (doctor) votes" in line
                rows.append({"id": did, "verdict": "illogical" if bad else "sound", "tag": "ignored_private_knowledge" if bad else "reasonable", "why": "scripted"})
        return json.dumps({"decisions": rows, "game": {"overall": 4, "summary": "scripted"}})


def test_judge_game_joins_verdicts_to_the_decisions_and_retries_unusable_replies():
    judge = Judge(bad_first=True)
    res = judge_game(small_game(), judge)
    assert judge.calls == 2 and res["ok"] and res["overall"] == 4
    assert [d["verdict"] for d in res["decisions"]] == ["sound", "sound", "sound", "illogical", "sound"]
    assert res["decisions"][3]["player"] == "Cy" and res["decisions"][3]["kind"] == "vote"
    always_bad = type("B", (), {"model": "b", "chat": lambda self, *a, **k: "nope"})()
    assert judge_game(small_game(), always_bad)["ok"] is False


def test_a_cut_off_reply_is_retried_with_a_different_prompt():
    class Cutoff(Judge):
        def __init__(self):
            super().__init__()
            self.seen = []

        def chat(self, messages, max_tokens=300, temperature=0.8):
            self.seen.append((messages[-1]["content"], max_tokens))
            if len(self.seen) == 1:  # the first reply rates only one of the five decisions, like a truncated reply
                return json.dumps({"decisions": [{"id": "D1", "verdict": "sound", "tag": "reasonable", "why": "x"}]})
            return super().chat(messages, max_tokens, temperature)

    j = Cutoff()
    res = judge_game(small_game(), j)
    assert res["ok"] and len(res["decisions"]) == 5 and len(j.seen) == 2
    assert j.seen[0][0] != j.seen[1][0]            # a changed prompt, so a cached bad reply cannot come back
    assert all(mt >= 16000 for _, mt in j.seen)    # room for a thinking model's hidden reasoning


def test_batch_judging_resumes_and_summarizes(tmp_path):
    log = tmp_path / "game_1.jsonl"
    log.write_text("\n".join(json.dumps(e) for e in small_game()) + "\n", encoding="utf-8")
    summary = tmp_path / "b.json"
    summary.write_text(json.dumps({"results": [{"seed": 1, "game_id": "game_1", "status": "finished"},
                                               {"seed": 2, "game_id": "game_2", "status": "error"}]}), encoding="utf-8")
    judge = Judge()
    out = tmp_path / "j.json"
    data = judge_batch(summary, judge, out, progress=lambda m: None)
    assert judge.calls == 1 and set(data["games"]) == {"game_1"}
    judge_batch(summary, judge, out, progress=lambda m: None)
    assert judge.calls == 1                                                      # a finished game is not judged twice
    s = summarize_judgements(json.loads(out.read_text()))
    assert s["games"] == 1 and s["decisions"] == 5 and s["all"]["illogical"] == 20.0 and s["all"]["sound"] == 80.0
    assert s["by_role"]["doctor"]["illogical"] == 50.0 and s["by_kind"]["vote"]["n"] == 2
    assert s["tags"] == {"ignored_private_knowledge": 1} and s["examples"][0]["player"] == "Cy" and s["overall_mean"] == 4.0
    # Cy (doctor) voted for Di, whom their own protection showed to be town: a hard check violation the judge caught.
    # Bob (detective) voted for the mafia he had found: a good act the judge rated sound.
    assert s["answer_key"] == {"violations": 1, "violations_flagged": 1, "violations_illogical": 1, "good_acts": 1, "good_acts_sound": 1}


def _judged(verdicts, overall=3, model="m"):
    rows = [{"id": f"D{i + 1}", "verdict": v, "tag": "other", "why": f"{v} {i + 1}", "player": "Bee", "role": "villager", "kind": "vote", "day": 1,
             "target": "Cee"} for i, v in enumerate(verdicts)]
    return {"model": model, "games": {"game_1": {"ok": True, "overall": overall, "decisions": rows}}}


def test_judges_that_agree_perfectly_score_one_and_the_kappa_discounts_chance():
    from mafia.judge import compare_judges

    a = _judged(["sound", "sound", "weak", "illogical"], 4)
    r = compare_judges(a, _judged(["sound", "sound", "weak", "illogical"], 4))
    assert r["decisions"] == 4 and r["exact_pct"] == 100.0 and r["kappa_sound_vs_not"] == 1.0 and r["illogical_both"] == 1
    # one judge calls everything sound: they agree on half the decisions, but no better than chance
    r = compare_judges(_judged(["sound"] * 4, 5), _judged(["sound", "weak", "sound", "weak"], 3))
    assert r["sound_vs_not_pct"] == 50.0 and r["kappa_sound_vs_not"] == 0.0 and r["overall_score_mean_abs_diff"] == 2.0


def test_flat_disagreements_and_unshared_games_are_handled():
    from mafia.judge import compare_judges

    a = _judged(["illogical", "sound", "weak"])
    b = _judged(["sound", "sound", "illogical"])
    r = compare_judges(a, b)
    assert r["illogical_either"] == 2 and r["illogical_both"] == 0
    assert [(d["id"], d["a"], d["b"]) for d in r["flat_disagreements"]] == [("D1", "illogical", "sound")]
    other = {"model": "z", "games": {"game_99": a["games"]["game_1"]}}
    r = compare_judges(a, other)
    assert r["decisions"] == 0 and r["exact_pct"] is None and r["kappa_sound_vs_not"] is None


def test_max_games_judges_only_the_first_seeds_in_order(tmp_path):
    for i in (1, 2, 3):
        (tmp_path / f"game_{i}.jsonl").write_text("\n".join(json.dumps(e) for e in small_game()) + "\n", encoding="utf-8")
    summary = tmp_path / "b.json"
    # listed out of order on purpose: seed order, not list order, decides which games are judged
    summary.write_text(json.dumps({"results": [{"seed": 12, "game_id": "game_3", "status": "finished"},
                                               {"seed": 10, "game_id": "game_1", "status": "finished"},
                                               {"seed": 11, "game_id": "game_2", "status": "finished"}]}), encoding="utf-8")
    judge = Judge()
    data = judge_batch(summary, judge, tmp_path / "j.json", progress=lambda m: None, max_games=2)
    assert set(data["games"]) == {"game_1", "game_2"} and judge.calls == 2


def test_log_without_setup_is_rejected():
    with pytest.raises(ValueError):
        build_casebook([ev("start")])
