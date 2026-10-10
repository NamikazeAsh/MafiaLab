from __future__ import annotations

import json
import sys
from pathlib import Path

from mafia.ablate import compare_arms, arm_rows, doctor_vote_cases
from mafia.analysis import aggregate, analyze_batch
from mafia.audit import audit_batch
from mafia.charts import bars_with_range, dumbbell, kpi_row, stacked_bars
from mafia.judge import summarize_judgements

LOGS = Path("logs")
OUT = Path("docs/images")
BATCHES = (("Baseline, 3.5 lite", "batch_main"), ("Shuffled, 3.5 lite", "batch_shuffle"), ("Shuffled, 3.1 lite", "batch_model31"))


def judged(batch: str) -> dict:
    return json.loads((LOGS / f"judge36_{batch}.json").read_text(encoding="utf-8"))


def row(label: str, s: dict, n_label: str | None = None) -> dict:
    return {"label": label, "n_label": n_label or f"{s['n']} decisions", "sound": s["sound"], "weak": s["weak"], "illogical": s["illogical"]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    per_batch = {label: summarize_judgements(judged(b)) for label, b in BATCHES}
    merged = {"model": "gemini-3.6-flash", "games": {}}
    for _, b in BATCHES:
        merged["games"].update(judged(b)["games"])
    allj = summarize_judgements(merged)

    # headline numbers
    prompts = sum(audit_batch(LOGS / f"{b}.json")["calls"] for _, b in BATCHES)
    leaks = sum(len(audit_batch(LOGS / f"{b}.json")["leaks"]) for _, b in BATCHES)
    ill = round(allj["decisions"] * allj["all"]["illogical"] / 100)
    cases = doctor_vote_cases([LOGS / "batch_main.json", LOGS / "batch_shuffle.json"], models={"gemini-3.5-flash-lite"})
    data = json.loads((LOGS / "ablate_doctor.json").read_text(encoding="utf-8"))
    comp = compare_arms(cases, arm_rows(data, "control"), arm_rows(data, "note"))
    c, n = comp["control"], comp["treatment"]
    tiles = [
        {"label": "Information leaks", "value": str(leaks), "note": f"in {prompts} prompts, 30 games"},
        {"label": "Decisions rated illogical", "value": f"{allj['all']['illogical']}%", "note": f"{ill} of {allj['decisions']}, judged on logic"},
        {"label": "Villager decisions sound", "value": f"{allj['by_role']['villager']['sound']}%", "note": "the weak spot: thin evidence"},
        {"label": "Doctor mistake with notes", "value": f"{n['voted_proven_town']} of {n['votes']}", "note": f"was {c['voted_proven_town']} of {c['votes']} without"},
    ]
    (OUT / "chart_headlines.svg").write_text(kpi_row(tiles, "Headline results"), encoding="utf-8")

    roles = [("Villager", "villager"), ("Doctor", "doctor"), ("Detective", "detective"), ("Mafia", "mafia")]
    (OUT / "chart_verdicts_by_role.svg").write_text(stacked_bars(
        "How each role's decisions were rated",
        f"Share of {allj['decisions']} decisions in 30 games, rated against only what the player knew",
        [row(label, allj["by_role"][k]) for label, k in roles]), encoding="utf-8")

    (OUT / "chart_verdicts_by_batch.svg").write_text(stacked_bars(
        "The three batches look alike",
        "Share of decisions rated sound, weak, or illogical. The differences are within noise (p = 0.36 to 0.90)",
        [row(label, per_batch[label]["all"], f"{per_batch[label]['decisions']} decisions") for label, _ in BATCHES]), encoding="utf-8")

    def aggregated(batch_file: str) -> dict:
        batch, games = analyze_batch(LOGS / batch_file)
        return aggregate(games, [r for r in batch["results"] if r["status"] == "finished"])

    base, shuf, other = aggregated("batch_main.json"), aggregated("batch_shuffle.json"), aggregated("batch_model31.json")
    labels = {"check": "Detective check", "kill": "Mafia kill", "save": "Doctor protection", "vote": "Day vote"}
    rows = [{"label": labels[k], "before": base["position"][k]["prompt_first_pct"], "after": shuf["position"][k]["prompt_first_pct"],
             "after2": other["position"][k]["prompt_first_pct"], "chance": shuf["position"][k]["prompt_chance_pct"]} for k in ("check", "kill", "save", "vote")]
    (OUT / "chart_position_bias.svg").write_text(dumbbell(
        "Shuffling fixed list position bias for one model, not the other",
        "How often the choice went to the name listed first in the prompt", rows, second_label="3.1 lite, shuffled"), encoding="utf-8")

    def arm(name: str, label: str, sub: str) -> dict:
        s = compare_arms(cases, arm_rows(data, "control"), arm_rows(data, name))["treatment"]
        lo, hi = [x / 100 for x in compare_arms(cases, arm_rows(data, "control"), arm_rows(data, name))["treatment_ci"]]
        return {"key": name, "label": label, "sub": f"{s['voted_proven_town']} of {s['votes']} votes", "value": 100 * s["voted_proven_town"] / s["votes"],
                "lo": 100 * lo, "hi": 100 * hi}
    ctl = {"key": "control", "label": "No change", "sub": f"{c['voted_proven_town']} of {c['votes']} votes", "value": 100 * c["voted_proven_town"] / c["votes"],
           "lo": comp["control_ci"][0], "hi": comp["control_ci"][1]}
    (OUT / "chart_doctor_replay.svg").write_text(bars_with_range(
        "Telling the doctor their own conclusion removes the mistake",
        "Share of the doctor's votes that went to a player their own protection had proved was town (95% range)",
        [ctl, arm("treatment", "General rule", ""), arm("note", "Own notes", "")], highlight="note",
        note="19 real prompts, 8 fresh replies each. All 16 mistakes came from 2 prompts, and the rule fixed only one of them."), encoding="utf-8")
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("chart_*.svg"))))


if __name__ == "__main__":
    main()
