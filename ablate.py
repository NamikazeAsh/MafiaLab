from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mafia.ablate import (DOCTOR_HINT, VILLAGER_HINT, arm_rows, compare_arms, compare_villager_arms, doctor_note, doctor_vote_cases,
                          judge_pairs, run_experiment, run_extra_arm, summarize_pairs, villager_vote_cases, with_user_note)
from mafia.llm.client import ChatClient
from mafia.setup import load_env


def doctor(a):
    cases = doctor_vote_cases(a.batches or ["logs/batch_main.json", "logs/batch_shuffle.json"], models={a.model})
    print(f"{len(cases)} real doctor votes where the doctor's own protection had proved a living player was town")
    client = ChatClient(model=a.model, rpm=a.rpm, cache_dir=None)   # no cache: every sample must be a fresh reply
    data = run_experiment(cases, client, DOCTOR_HINT, a.samples, a.out)
    r = compare_arms(cases, arm_rows(data, "control"), arm_rows(data, "treatment"))
    c, t = r["control"], r["treatment"]
    pct = lambda s: f"{round(100 * s['voted_proven_town'] / max(1, s['votes']), 1)}%"
    print(f"\n{'':34}{'control':>12}{'with hint':>12}")
    for label, key in (("replies", "samples"), ("unusable replies", "invalid"), ("abstained", "abstained"), ("votes cast", "votes"),
                       ("voted the proven town player", "voted_proven_town"), ("voted the real mafia", "voted_mafia")):
        print(f"{label:34}{c[key]:>12}{t[key]:>12}")
    print(f"{'proven town player, share of votes':34}{pct(c):>12}{pct(t):>12}")
    print(f"{'  95% range':34}{str(r['control_ci']):>12}{str(r['treatment_ci']):>12}")
    print(f"Fisher exact p = {r['fisher_p']}   prompts improved {r['cases_improved']}, worse {r['cases_worse']}, of {r['cases']}")

    if a.note_arm:
        data = run_extra_arm(cases, client, data, "note", lambda case: (lambda m: with_user_note(m, doctor_note(case))), a.samples, a.out)
        n = compare_arms(cases, arm_rows(data, "control"), arm_rows(data, "note"))
        s = n["treatment"]
        print(f"\nThe doctor's own conclusion stated as a fact, instead of a rule (example note: \"{doctor_note(cases[0])}\")")
        print(f"{'':34}{'control':>12}{'with note':>12}")
        for label, key in (("votes cast", "votes"), ("abstained", "abstained"), ("voted the proven town player", "voted_proven_town"), ("voted the real mafia", "voted_mafia")):
            print(f"{label:34}{c[key]:>12}{s[key]:>12}")
        print(f"{'proven town player, share of votes':34}{pct(c):>12}{pct(s):>12}")
        print(f"{'  95% range':34}{str(n['control_ci']):>12}{str(n['treatment_ci']):>12}")
        print(f"Fisher exact p = {n['fisher_p']}   prompts improved {n['cases_improved']}, worse {n['cases_worse']}, of {n['cases']}")
        bad = [i for i, cs in enumerate(cases) if any(r_["target"] in cs["blocked"] for arm_ in ("control", "treatment", "note") for r_ in data[arm_][str(i)])]
        print("\nThe prompts where any arm voted the proven town player:")
        for i in bad:
            counts = {arm_: sum(1 for r_ in data[arm_][str(i)] if r_["target"] in cases[i]["blocked"]) for arm_ in ("control", "treatment", "note")}
            print(f"  case {i} ({cases[i]['game'][-8:]}): control {counts['control']}/{a.samples}, rule {counts['treatment']}/{a.samples}, note {counts['note']}/{a.samples}")


def villager(a):
    cases = villager_vote_cases(a.batches or ["logs/batch_model31.json"], models={a.model}, max_cases=a.max_cases, seed=a.seed)
    print(f"{len(cases)} real villager day votes sampled")
    client = ChatClient(model=a.model, rpm=a.rpm, cache_dir=None)
    data = run_experiment(cases, client, VILLAGER_HINT, a.samples, a.out)
    r = compare_villager_arms(cases, arm_rows(data, "control"), arm_rows(data, "treatment"))
    c, t = r["control"], r["treatment"]
    print(f"\n{'':44}{'control':>12}{'with hint':>12}{'p':>9}")
    for label, key in (("replies", "samples"), ("unusable replies", "invalid"), ("abstained", "abstained"), ("votes cast", "votes")):
        print(f"{label:44}{c.get(key, 0):>12}{t.get(key, 0):>12}")
    for label, key in (("reason cites concrete evidence", "basis_concrete"), ("reason cites nothing specific", "basis_none"),
                       ("reason invents a vote record", "invented_vote_record"), ("vote hits the real mafia", "hit_mafia")):
        x = r[key]
        print(f"{label:44}{str(x['control_pct']) + '%':>12}{str(x['treatment_pct']) + '%':>12}{x['p']:>9}")
    if a.judge_pairs:
        jc = ChatClient(model=a.judge_model, rpm=10)
        try:
            judge_pairs(cases, data, jc, a.judge_pairs, seed=a.seed)
        except RuntimeError as e:
            print(f"Judge stopped: {e}")
        Path(a.out).write_text(json.dumps(data, indent=1), encoding="utf-8")
        s = summarize_pairs(list(data.get("pairs", {}).values()))
        print(f"\nBlind pairwise judge ({a.judge_model}), {s['pairs']} pairs: hint better {s['hint_wins']}, control better {s['control_wins']}, "
              f"ties {s['ties']}, sign test p = {s['sign_test_p']}")
        print(f"  replies the judge says invent facts: control {s['control_invents']}, hint {s['hint_invents']}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    ap = argparse.ArgumentParser(description="Replay real prompts with and without an added instruction.")
    ap.add_argument("experiment", choices=["doctor", "villager"], help="which weakness to test")
    ap.add_argument("--batches", nargs="+", default=None, help="batch summaries to take real prompts from")
    ap.add_argument("--model", default="gemini-3.5-flash-lite", help="the model to ask again (also filters prompts to batches played by it)")
    ap.add_argument("--samples", type=int, default=8, help="replies per prompt in each arm")
    ap.add_argument("--rpm", type=float, default=15)
    ap.add_argument("--max-cases", type=int, default=18, help="villager only: how many prompts to sample")
    ap.add_argument("--judge-model", default="gemini-3.8-flash", help="villager only: the blind pairwise judge")
    ap.add_argument("--judge-pairs", type=int, default=18, help="villager only: how many pairs the judge compares (0 to skip)")
    ap.add_argument("--note-arm", action="store_true", help="doctor only: also test stating the conclusion as a fact in the player's own notes")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    a.out = a.out or f"logs/ablate_{a.experiment}.json"
    if not ChatClient(model=a.model).api_key:
        sys.exit("Set GEMINI_API_KEY first.")
    try:
        (doctor if a.experiment == "doctor" else villager)(a)
    except RuntimeError as e:
        sys.exit(f"Stopped: {e}\nRerun the same command to resume.")
    print(f"Saved to {Path(a.out)}")


if __name__ == "__main__":
    main()
