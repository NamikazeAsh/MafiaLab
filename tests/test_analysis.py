import json

import pytest

from mafia.analysis import (
    CLAIM, FORMAT_LEAK, HALLUCINATED_HISTORY, MAFIA_CONFESSION, SYCOPHANCY,
    aggregate, analyze_batch, analyze_game, jaccard, render_report, words,
)
from mafia.batch import run_batch


def ev(kind, day=1, phase="day", text="", **data):
    return {"idx": 0, "day": day, "phase": phase, "kind": kind, "text": text, "data": data, "visible_to": None}


ROLES = {"Ann": "mafia", "Bob": "detective", "Cy": "doctor", "Di": "villager", "Ed": "villager", "Flo": "villager"}


def game(*events):
    return [ev("setup", 0, "night", roles=ROLES, players=list(ROLES)), *events]


def test_text_patterns():
    assert CLAIM["doctor"].search("I am the doctor and I protected Bob")
    assert CLAIM["doctor"].search("my protection worked")
    assert CLAIM["detective"].search("I investigated Cy last night")
    assert not CLAIM["doctor"].search("the doctor is probably quiet")
    assert MAFIA_CONFESSION.search("As mafia we should stay calm")
    assert not MAFIA_CONFESSION.search("Ann seems like mafia to me")
    assert FORMAT_LEAK.search('[night 2] [mafia] Di: hi') and FORMAT_LEAK.search('{"say": "hi"}')
    assert not FORMAT_LEAK.search("I think Bob is suspicious.")
    assert HALLUCINATED_HISTORY.search("Nobody died yesterday") and not HALLUCINATED_HISTORY.search("Nobody died last night")
    assert SYCOPHANCY.search("Bob makes a really good point") and SYCOPHANCY.search("I completely agree")
    assert not SYCOPHANCY.search("I suspect Bob because of his votes")


def test_quoted_claims_are_not_counted_as_the_speakers_own():
    from mafia.analysis import strip_quotes

    quoted = "Bob has stated, 'I am the detective, and I investigated Ann last night,' but I doubt it."
    assert not CLAIM["detective"].search(strip_quotes(quoted))
    assert not CLAIM["detective"].search(strip_quotes('Bob said "I am the detective" earlier.'))
    assert CLAIM["detective"].search(strip_quotes("I don't trust this. I am the detective, and I checked Ann."))
    assert "don't" in strip_quotes("I don't think that's right, Cy's plan is odd.")  # apostrophes are not quotes
    events = game(
        ev("speech", speaker="Di", message=quoted),
        ev("speech", speaker="Ed", message="Actually I am the detective, and I checked Cy last night."),
    )
    assert analyze_game(events, "g")["counts"]["fake_power_claims"] == 1  # only Ed's own claim, not the quote


def test_helpers():
    assert words("Hello, World! It's fine") == ["hello", "world", "it's", "fine"]
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0 and jaccard({"a"}, {"b"}) == 0.0 and jaccard(set(), {"a"}) == 0.0


def test_analyze_counts_leaks_claims_and_votes():
    events = game(
        ev("speech", speaker="Cy", message="My protection worked last night, I am the doctor."),
        ev("speech", speaker="Ann", message="As mafia we should stay calm and quiet, my partner agrees."),
        ev("speech", speaker="Di", message="I am the detective and I investigated Ann."),
        ev("speech", speaker="Ed", message="[night 2] Ed: something leaked into this speech"),
        ev("speech", speaker="Flo", message="Nobody died yesterday which is strange to me today."),
        # Di and Ed (town) vote: one hits the mafia, one misses. Flo abstains.
        ev("vote", voter="Di", target="Ann"),
        ev("vote", voter="Ed", target="Bob"),
        ev("vote", voter="Flo", target=None),
        ev("vote", voter="Ann", target="Ann"),
        ev("death", victim="Bob", role="detective", cause="vote"),
        ev("end", winner="mafia", roles=ROLES),
    )
    r = analyze_game(events, "game_1")["counts"]
    assert r["speeches"] == 5
    assert r["doctor_self_claim_speeches"] == 1
    assert r["fake_power_claims"] == 1          # Di is a villager claiming to be the detective
    assert r["mafia_confessions"] == 1
    assert r["format_leaks"] == 1
    assert r["hallucinated_history"] == 1
    assert r["town_votes"] == 3 and r["town_votes_on_mafia"] == 1 and r["town_abstain"] == 1
    assert r["mafia_votes_on_partner"] == 1
    assert r["lynches"] == 1 and r["lynch_power"] == 1 and r["lynch_town"] == 1


def test_night_metrics_saves_repeats_and_detective_followthrough():
    events = game(
        ev("kill_decision", 1, "night", target="Bob"),
        ev("save", 1, "night", actor="Cy", target="Bob"),
        ev("investigate", 1, "night", actor="Bob", target="Ann", result="MAFIA"),
        ev("no_death", 1, "day"),
        ev("speech", 1, "day", speaker="Bob", message="Ann is the mafia, I checked her."),
        ev("kill_decision", 2, "night", target="Bob"),          # mafia retries the blocked target
        ev("save", 2, "night", actor="Cy", target="Bob"),        # doctor repeats the same target
        ev("no_death", 2, "day"),
    )
    r = analyze_game(events, "game_2")["counts"]
    assert r["night_kills"] == 2 and r["kills_saved"] == 2 and r["kills_on_power"] == 2
    assert r["mafia_repeat_after_save"] == 1
    assert r["doctor_saves"] == 2 and r["doctor_repeat_target"] == 1 and r.get("doctor_self_protect", 0) == 0
    assert r["detective_found_mafia"] == 1 and r["detective_reported"] == 1


def test_position_bias_counts_first_listed_choices():
    # Alive order is Ann, Bob, Cy, Di, Ed, Flo. Ann is mafia, so kill options are Bob, Cy, Di, Ed, Flo.
    events = game(
        ev("kill_decision", 1, "night", target="Bob"),                       # first option
        ev("save", 1, "night", actor="Cy", target="Ann"),                    # first option of all six
        ev("investigate", 1, "night", actor="Bob", target="Cy", result="not mafia"),  # options exclude Bob: Ann is first, Cy is not
        ev("vote", voter="Di", target="Ann"),                                # first option for Di
        ev("vote", voter="Ed", target=None),                                 # abstain is ignored
    )
    c = analyze_game(events, "g")["counts"]
    assert (c["pos_n_kill"], c["pos_first_kill"], c["pos_exp_kill"]) == (1, 1, 200)
    assert (c["pos_n_save"], c["pos_first_save"], c["pos_exp_save"]) == (1, 1, 167)
    assert (c["pos_n_check"], c["pos_first_check"]) == (1, 0)
    assert (c["pos_n_vote"], c["pos_first_vote"]) == (1, 1)
    a = aggregate([analyze_game(events, "g")], [])
    kill = a["position"]["kill"]
    assert (kill["n"], kill["first_pct"], kill["chance_pct"]) == (1, 100.0, 20.0)
    assert kill["prompt_n"] == 0  # no prompt trace was given for this game


def test_prompt_position_is_read_from_the_saved_prompts(tmp_path):
    from mafia.analysis import prompt_position, trace_for

    def row(verb, shown, target):
        user = f"Game so far:\n...\n\nChoose who {verb}. Options: {', '.join(shown)}.\nReply with only JSON."
        return json.dumps({"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": user}],
                           "response": json.dumps({"reason": "r", "target": target})})

    trace = tmp_path / "trace_1000.jsonl"
    trace.write_text("\n".join([
        row("the mafia kills tonight", ["Cy", "Bob", "Ed"], "Cy"),            # first listed
        row("to protect tonight", ["Ed", "Ann", "Cy", "Bob"], "Bob"),          # last listed
        row("to investigate tonight", ["Di", "Ann"], "Di"),                   # first listed
        row("to vote out", ["Ann", "Bob", "Cy", "Di", "Ed"], "Ed"),           # last listed
        '{"messages": [{"role": "user", "content": "say something"}], "response": "hello"}',   # speech is ignored
    ]) + "\n", encoding="utf-8")
    c = prompt_position(trace)
    assert (c["ppos_n_kill"], c["ppos_first_kill"], c["ppos_exp_kill"]) == (1, 1, 333)
    assert (c["ppos_n_save"], c["ppos_first_save"]) == (1, 0)
    assert (c["ppos_n_check"], c["ppos_first_check"]) == (1, 1)
    assert (c["ppos_n_vote"], c["ppos_first_vote"]) == (1, 0)
    assert prompt_position(None) == {}
    assert trace_for(tmp_path, "game_1001") == trace and trace_for(tmp_path, "game_5000") is None


def test_near_duplicates_and_variety():
    same = "I think we should look carefully at who has been quiet during this whole discussion today"
    events = game(
        ev("speech", speaker="Di", message=same),
        ev("speech", speaker="Ed", message=same + " honestly"),
        ev("speech", speaker="Flo", message="Completely different thoughts about voting patterns and alibis from Monday night."),
    )
    g = analyze_game(events, "game_3")
    assert g["counts"]["near_duplicate_speeches"] == 2
    assert g["examples"]["dups"] and 0 < g["distinct2"] <= 1


def test_log_without_setup_is_rejected():
    with pytest.raises(ValueError):
        analyze_game([ev("start")])


def test_comparison_pairs_seeds_and_lists_both_batches(tmp_path):
    from mafia.analysis import render_comparison

    run_batch(3, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "a.json", seed_start=1, progress=lambda m: None)
    run_batch(3, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "b.json", seed_start=2, progress=lambda m: None)
    ba, ga = analyze_batch(tmp_path / "a.json")
    bb, gb = analyze_batch(tmp_path / "b.json")
    text = render_comparison("old", ba, ga, "new", bb, gb)
    assert "# Comparison: old against new" in text and "| Metric | old | new | Note |" in text
    assert "Detective check: earliest seat" in text and "first listed in prompt" in text
    assert "## Same seeds, same roles" in text
    section = text.split("## Same seeds, same roles")[1]
    seeds = [ln.split("|")[1].strip() for ln in section.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip().isdigit()]
    assert seeds == ["2", "3"]  # batch a used seeds 1 to 3 and batch b used 2 to 4, so only 2 and 3 overlap


def test_report_includes_the_audit_section_when_given(tmp_path):
    run_batch(2, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "c.json", seed_start=1, progress=lambda m: None)
    batch, games = analyze_batch(tmp_path / "c.json")
    audit = {"games": 2, "skipped": 0, "calls": 120, "history_lines": 4500, "leaks": [], "role_mismatches": 0, "teammate_mismatches": 0}
    text = render_report(batch, games, audit)
    assert "## Information leak audit" in text and "| Prompts checked | 120 |" in text and "| Leaks | 0 |" in text
    assert "Information leak audit" not in render_report(batch, games)


def test_report_includes_the_judge_review_when_given(tmp_path):
    run_batch(2, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "d.json", seed_start=1, progress=lambda m: None)
    batch, games = analyze_batch(tmp_path / "d.json")
    share = lambda n, s, w, i: {"n": n, "sound": s, "weak": w, "illogical": i}
    judged = {"model": "judge-x", "games": 2, "failed": 0, "decisions": 40, "all": share(40, 70.0, 22.5, 7.5),
              "by_kind": {"vote": share(30, 60.0, 30.0, 10.0), "protect": share(0, None, None, None), "check": share(5, 100.0, 0.0, 0.0), "mafia kill": share(5, 80.0, 20.0, 0.0)},
              "by_role": {"villager": share(10, 50.0, 40.0, 10.0), "doctor": share(0, None, None, None), "detective": share(10, 90.0, 10.0, 0.0), "mafia": share(20, 70.0, 20.0, 10.0)},
              "overall_mean": 3.5, "tags": {"unsupported_accusation": 5}, "examples": [{"game": "game_123456", "day": 2, "player": "Bee", "role": "doctor", "kind": "vote", "target": "Cee", "why": "Ignored its own save."}],
              "answer_key": {"violations": 2, "violations_flagged": 2, "violations_illogical": 1, "good_acts": 3, "good_acts_sound": 3}}
    text = render_report(batch, games, None, judged)
    assert "## Judge review" in text and "`judge-x`" in text and "| All | 40 | 70.0% | 22.5% | 7.5% |" in text
    assert "rated 2 of 2 as weak or illogical (1 as illogical)" in text and "rated 3 of 3 as sound" in text
    assert "Ignored its own save." in text and "unsupported accusation (5)" in text
    assert "Judge review" not in render_report(batch, games)


def test_comparison_adds_judge_rows_only_when_both_batches_have_them(tmp_path):
    from mafia.analysis import render_comparison

    run_batch(2, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "e.json", seed_start=1, progress=lambda m: None)
    run_batch(2, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "f.json", seed_start=1, progress=lambda m: None)
    ba, ga = analyze_batch(tmp_path / "e.json")
    bb, gb = analyze_batch(tmp_path / "f.json")
    share = lambda n, s, w, i: {"n": n, "sound": s, "weak": w, "illogical": i}

    def js(sound, ill, score, games):
        return {"model": "j", "games": games, "decisions": 30, "all": share(30, sound, 100 - sound - ill, ill), "overall_mean": score,
                "by_kind": {"vote": share(20, sound - 10, 0, 0)}, "by_role": {"villager": share(10, sound - 20, 0, 0)}}

    text = render_comparison("old", ba, ga, "new", bb, gb, js(70.0, 5.0, 3.0, 6), js(80.0, 2.5, 3.8, 6))
    assert "## Judge review (same seeds, same judge)" in text and "| Sound | 70.0% | 80.0% |" in text and "| Game logic score, 1 to 5 | 3.0 | 3.8 |" in text
    assert "Judge review" not in render_comparison("old", ba, ga, "new", bb, gb, js(70.0, 5.0, 3.0, 6), None)


def test_full_pipeline_on_random_games(tmp_path):
    run_batch(4, use_random=True, log_dir=tmp_path, summary_path=tmp_path / "b.json", seed_start=1, progress=lambda m: None)
    batch, games = analyze_batch(tmp_path / "b.json")
    assert len(games) == 4
    a = aggregate(games, batch["results"])
    assert a["games"] == 4 and a["town_wins"] + a["mafia_wins"] == 4
    assert a["speeches"] == sum(g["counts"]["speeches"] for g in games)
    assert 0 <= a["near_duplicate_pct"] <= 100 and a["format_leaks"] == 0
    report = render_report(batch, games)
    assert "# Batch quality report" in report and "Town vote accuracy" in report
