import json

import pytest

from mafia.ablate import (DOCTOR_HINT, compare_arms, doctor_vote_cases, fisher_two_sided, run_arm, score_arm, wilson, with_hint)

ROLES = {"Ann": "mafia", "Bob": "detective", "Cy": "doctor", "Di": "villager", "Ed": "villager", "Flo": "villager"}


def doctor_prompt(history, options):
    system = "RULES...\n\nYour name is Cy. You are the DOCTOR. Keep your role secret."
    user = "Game so far:\n" + "\n".join(history) + "\n\nIt is day 2. Alive: Ann, Bob, Cy, Di.\n\n" \
           f'Choose who to vote out. Options: {", ".join(options)}.\nReply with only JSON.'
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def make_batch(tmp_path, rows_by_game, model="gemini-3.5-flash-lite"):
    results = []
    for i, (history, options, reply) in enumerate(rows_by_game, start=1):
        gid = f"game_{1000 + i}"
        events = [{"idx": 0, "day": 0, "phase": "night", "kind": "setup", "text": "", "data": {"roles": ROLES, "players": list(ROLES)}, "visible_to": []}]
        (tmp_path / f"{gid}.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        (tmp_path / f"trace_{1000 + i}.jsonl").write_text(
            json.dumps({"messages": doctor_prompt(history, options), "response": reply}) + "\n", encoding="utf-8")
        results.append({"seed": i, "game_id": gid, "status": "finished"})
    summary = tmp_path / "b.json"
    summary.write_text(json.dumps({"config": {"model": model}, "results": results}), encoding="utf-8")
    return summary


def test_only_real_situations_where_the_protection_proved_someone_town_become_cases(tmp_path):
    proof = ["[night 1] You protect Di.", "[day 1] Nobody died last night.", "[day 1] Bob: hello"]
    no_proof = ["[night 1] You protect Di.", "[day 1] Ed was killed in the night. They were villager."]   # someone died
    other_night = ["[night 1] You protect Di.", "[day 2] Nobody died last night."]                          # a different day
    dead_target = ["[night 1] You protect Ed.", "[day 1] Nobody died last night."]                         # Ed is not an option any more
    s = make_batch(tmp_path, [(proof, ["Ann", "Bob", "Di"], '{"target": "Di"}'), (no_proof, ["Ann", "Bob", "Di"], '{"target": "Ann"}'),
                              (other_night, ["Ann", "Bob", "Di"], '{"target": "Ann"}'), (dead_target, ["Ann", "Bob", "Di"], '{"target": "Ann"}')])
    cases = doctor_vote_cases([s])
    assert len(cases) == 1 and cases[0]["blocked"] == ["Di"] and cases[0]["player"] == "Cy"
    assert cases[0]["mafia"] == ["Ann"] and cases[0]["original_target"] == "Di" and cases[0]["options"] == ["Ann", "Bob", "Di"]


def test_the_model_filter_keeps_only_batches_of_that_model(tmp_path):
    proof = ["[night 1] You protect Di.", "[day 1] Nobody died last night."]
    s = make_batch(tmp_path, [(proof, ["Ann", "Di"], '{"target": "Di"}')], model="other-model")
    assert doctor_vote_cases([s], models={"gemini-3.5-flash-lite"}) == [] and len(doctor_vote_cases([s])) == 1


def test_with_hint_changes_only_the_system_prompt():
    msgs = doctor_prompt(["x"], ["Ann", "Di"])
    out = with_hint(msgs, DOCTOR_HINT)
    assert out[0]["content"].endswith(DOCTOR_HINT) and out[0]["content"].startswith(msgs[0]["content"])
    assert out[1] == msgs[1] and "NOT mafia" not in msgs[0]["content"]              # the original is untouched


class Doctor:
    """A scripted model: votes for the proven town player unless the hint is present."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, max_tokens=300, temperature=0.8):
        self.calls += 1
        hinted = "NOT mafia" in messages[0]["content"]
        return json.dumps({"reason": "r", "target": "Ann" if hinted else "Di"})


def make_cases(tmp_path):
    proof = ["[night 1] You protect Di.", "[day 1] Nobody died last night."]
    return doctor_vote_cases([make_batch(tmp_path, [(proof, ["Ann", "Bob", "Di"], '{"target": "Di"}')] * 2)])


def test_arms_are_scored_and_compared(tmp_path):
    cases = make_cases(tmp_path)
    assert len(cases) == 2
    model = Doctor()
    control = run_arm(cases, model, lambda m: m, samples=4)
    treatment = run_arm(cases, model, lambda m: with_hint(m, DOCTOR_HINT), samples=4)
    assert model.calls == 16 and len(control) == 8
    res = compare_arms(cases, control, treatment)
    assert res["control"]["voted_proven_town"] == 8 and res["treatment"]["voted_proven_town"] == 0
    assert res["treatment"]["voted_mafia"] == 8 and res["fisher_p"] < 0.001 and res["cases_improved"] == 2 and res["cases_worse"] == 0


def test_the_experiment_saves_per_case_and_resumes_without_asking_again(tmp_path):
    from mafia.ablate import arm_rows, run_experiment

    cases = make_cases(tmp_path)
    out = tmp_path / "exp.json"
    model = Doctor()
    run_experiment(cases, model, DOCTOR_HINT, 3, out, progress=lambda m: None)
    assert model.calls == 2 * 2 * 3                      # two cases, two arms, three replies each
    again = Doctor()
    data = run_experiment(cases, again, DOCTOR_HINT, 3, out, progress=lambda m: None)
    assert again.calls == 0                              # everything was already saved
    assert len(arm_rows(data, "control")) == 6 and all(r["target"] == "Di" for r in arm_rows(data, "control"))
    assert all(r["target"] == "Ann" for r in arm_rows(data, "treatment"))


def test_invalid_replies_and_abstentions_are_not_counted_as_votes(tmp_path):
    cases = make_cases(tmp_path)

    class Odd:
        replies = iter(['{"target": null}', "gibberish", '{"target": "Di"}', '{"target": "Zed"}'] * 2)

        def chat(self, *a, **k):
            return next(self.replies)

    s = score_arm(cases, run_arm(cases, Odd(), lambda m: m, samples=4))
    assert (s["samples"], s["invalid"], s["abstained"], s["votes"], s["voted_proven_town"]) == (8, 4, 2, 2, 2)


def villager_prompt(history, options, me="Di"):
    system = f"RULES...\n\nYour name is {me}. You are a VILLAGER. You have no special power."
    user = "Game so far:\n" + "\n".join(history) + "\n\nIt is day 2. Alive: Ann, Bob, Di, Ed.\n\n" \
           f'Choose who to vote out. Options: {", ".join(options)}.\nReply with only JSON.'
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def make_villager_batch(tmp_path, history, options, reply='{"target": "Ann"}'):
    gid = "game_2001"
    events = [{"idx": 0, "day": 0, "phase": "night", "kind": "setup", "text": "", "data": {"roles": ROLES, "players": list(ROLES)}, "visible_to": []}]
    (tmp_path / f"{gid}.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    (tmp_path / "trace_2001.jsonl").write_text(json.dumps({"messages": villager_prompt(history, options), "response": reply}) + "\n"
                                               + json.dumps({"messages": doctor_prompt(history, options), "response": reply}) + "\n", encoding="utf-8")
    summary = tmp_path / "v.json"
    summary.write_text(json.dumps({"config": {"model": "m"}, "results": [{"seed": 1, "game_id": gid, "status": "finished"}]}), encoding="utf-8")
    return summary


def test_villager_cases_come_only_from_villager_votes(tmp_path):
    from mafia.ablate import villager_vote_cases

    s = make_villager_batch(tmp_path, ["[day 1] Ed votes for Ann."], ["Ann", "Bob", "Ed"])
    cases = villager_vote_cases([s])
    assert len(cases) == 1 and cases[0]["player"] == "Di" and cases[0]["mafia"] == ["Ann"]
    assert cases[0]["roster"] == ["Ann", "Bob", "Di", "Ed"] and cases[0]["history"] == ["[day 1] Ed votes for Ann."]
    assert villager_vote_cases([s], models={"other"}) == []


def test_the_note_states_the_conclusion_from_the_doctors_own_protections_and_leaves_the_prompt_intact(tmp_path):
    from mafia.ablate import doctor_note, with_user_note

    cases = make_cases(tmp_path)
    note = doctor_note(cases[0])
    assert "you protected Di on a night when nobody died" in note and "Di is NOT mafia" in note
    assert "Ann" not in note and "mafia" in note                                  # it never names the real mafia
    two = doctor_note({"blocked": ["Ann", "Bob"]})
    assert "Ann and Bob are NOT mafia" in two
    msgs = cases[0]["messages"]
    out = with_user_note(msgs, note)
    assert out[-1]["content"].endswith(note) and out[-1]["content"].startswith(msgs[-1]["content"]) and out[0] == msgs[0]
    assert note not in msgs[-1]["content"]                                          # the original is untouched


def test_an_extra_arm_is_added_per_case_and_resumes(tmp_path):
    from mafia.ablate import arm_rows, doctor_note, run_experiment, run_extra_arm, with_user_note

    cases = make_cases(tmp_path)
    out = tmp_path / "exp2.json"
    data = run_experiment(cases, Doctor(), DOCTOR_HINT, 2, out, progress=lambda m: None)

    class NoteModel:
        calls = 0

        def chat(self, messages, max_tokens=300, temperature=0.8):
            NoteModel.calls += 1
            return json.dumps({"reason": "r", "target": "Ann" if "NOT mafia" in messages[-1]["content"] else "Di"})

    arm = lambda case: (lambda m: with_user_note(m, doctor_note(case)))
    data = run_extra_arm(cases, NoteModel(), data, "note", arm, 2, out, progress=lambda m: None)
    assert NoteModel.calls == 4 and all(r["target"] == "Ann" for r in arm_rows(data, "note"))
    run_extra_arm(cases, NoteModel(), data, "note", arm, 2, out, progress=lambda m: None)
    assert NoteModel.calls == 4                                                     # saved cases are not asked again
    assert "note" in json.loads(out.read_text())


def test_the_experiment_runs_on_villager_cases_too(tmp_path):
    """Regression: the progress line once assumed every case has a 'blocked' field, which only doctor cases do."""
    from mafia.ablate import VILLAGER_HINT, arm_rows, run_experiment, villager_vote_cases

    cases = villager_vote_cases([make_villager_batch(tmp_path, ["[day 1] Ed votes for Ann."], ["Ann", "Bob", "Ed"])])
    lines = []

    class Model:
        def chat(self, messages, max_tokens=300, temperature=0.8):
            return json.dumps({"reason": "Ed voted for Ann", "target": "Ann"})

    data = run_experiment(cases, Model(), VILLAGER_HINT, 2, tmp_path / "experiment_out.json", progress=lines.append)
    assert len(arm_rows(data, "control")) == 2 and lines == ["case 1/1 done (game_2001)"]


def test_an_invented_vote_record_is_caught_and_a_real_one_is_not():
    from mafia.ablate import unsupported_vote_claims

    history = ["[day 1] Ed votes for Ann.", "[day 1] Bob votes for Ed."]
    roster = ["Ann", "Bob", "Di", "Ed"]
    assert unsupported_vote_claims("Ed voted for Ann, which looks coordinated.", history, roster) == 0
    assert unsupported_vote_claims("Bob voted against Ann, which looks odd.", history, roster) == 1        # Bob voted for Ed
    assert unsupported_vote_claims("Di voted for Ed yesterday.", history, roster) == 1                   # no such vote
    assert unsupported_vote_claims("ed voted for ann and Bob voted for Ed", history, roster) == 0          # case does not matter
    assert unsupported_vote_claims("Ann is acting defensive.", history, roster) == 0


def test_villager_arms_are_scored_for_basis_accuracy_and_inventions(tmp_path):
    from mafia.ablate import compare_villager_arms, villager_vote_cases

    cases = villager_vote_cases([make_villager_batch(tmp_path, ["[day 1] Ed votes for Ann."], ["Ann", "Bob", "Ed"])])
    row = lambda reason, target="Ann", invalid=False: {"case": 0, "sample": 0, "target": target, "invalid": invalid, "reason": reason}
    control = [row("Ann seems defensive."), row("no idea", "Bob"), row("whatever", None), row("junk", invalid=True)]
    treatment = [row("Ed voted for Ann yesterday, a vote record."), row("Bob voted for Ed, which was a vote record."), row("Ann claimed to be detective, a claim.")]
    res = compare_villager_arms(cases, control, treatment)
    assert res["control"]["votes"] == 2 and res["control"]["abstained"] == 1 and res["control"]["invalid"] == 1
    assert res["control"]["basis_behavior_only"] == 1 and res["control"]["basis_none"] == 1
    assert res["basis_concrete"]["control_pct"] == 0.0 and res["basis_concrete"]["treatment_pct"] == 100.0
    assert res["invented_vote_record"]["treatment_pct"] == 33.3 and res["hit_mafia"]["treatment_pct"] == 100.0


class PairJudge:
    """A scripted pairwise judge that prefers whichever reply mentions a vote."""

    def __init__(self):
        self.prompts = []

    def chat(self, messages, max_tokens=300, temperature=0.8):
        text = messages[0]["content"]
        self.prompts.append(text)
        a = text.split("=== REPLY A ===")[1].split("=== REPLY B ===")[0]
        better = "A" if "vote" in a else "B"
        return json.dumps({"better": better, "a_invents_facts": False, "b_invents_facts": "made up" in text, "why": "scripted"})


def test_pairs_are_blinded_randomized_and_unblinded_correctly(tmp_path):
    from mafia.ablate import judge_pairs, summarize_pairs, villager_vote_cases

    cases = villager_vote_cases([make_villager_batch(tmp_path, ["[day 1] Ed votes for Ann."], ["Ann", "Bob", "Ed"])] * 1)
    data = {"control": {}, "treatment": {}}
    for i in range(12):                      # twelve identical cases give twelve pairs, with a mix of A and B positions
        cases.append(cases[0])
    for i in range(len(cases)):
        data["control"][str(i)] = [{"case": i, "sample": 0, "target": "Ann", "invalid": False, "reason": "Ann seems defensive."}]
        data["treatment"][str(i)] = [{"case": i, "sample": 0, "target": "Ann", "invalid": False, "reason": "Ed's vote record points at Ann."}]
    judge = PairJudge()
    pairs = judge_pairs(cases, data, judge, max_pairs=10, seed=1, progress=lambda m: None)
    assert len(pairs) == 10 and all(p["winner"] == "hint" for p in pairs)       # the hint reply always mentions a vote
    assert any("REPLY A ===\nVote: Ann\nReason: Ed's vote" in t for t in judge.prompts) and any("REPLY A ===\nVote: Ann\nReason: Ann seems" in t for t in judge.prompts)
    assert "hint" not in judge.prompts[0].lower().split("=== the situation ===")[0] and "control" not in judge.prompts[0].lower()
    s = summarize_pairs(pairs)
    assert s["hint_wins"] == 10 and s["control_wins"] == 0 and s["sign_test_p"] < 0.01
    again = judge_pairs(cases, data, PairJudge(), max_pairs=10, seed=1, progress=lambda m: None)
    assert len(again) == 10                                                      # saved pairs are not asked again


def test_sign_test_of_an_even_split_is_not_significant():
    from mafia.ablate import summarize_pairs

    s = summarize_pairs([{"winner": "hint", "invents": {"control": False, "hint": False}}] * 5 + [{"winner": "control", "invents": {"control": True, "hint": False}}] * 5)
    assert s["sign_test_p"] == 1.0 and s["control_invents"] == 5 and s["hint_invents"] == 0


def test_statistics_helpers():
    assert fisher_two_sided(8, 0, 0, 8) < 0.001 and fisher_two_sided(4, 4, 4, 4) == pytest.approx(1.0)
    lo, hi = wilson(0, 20)
    assert lo == 0.0 and 0.1 < hi < 0.2
    assert wilson(0, 0) == (0.0, 0.0)
