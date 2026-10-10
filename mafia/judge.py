"""An LLM judge that rates each key decision by what the player knew when they made it.

The judge reads a casebook with full knowledge of the game, but it is told to rate every decision against
only the information that player had, and never by who turned out to be right.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .analysis import load_events, trace_for  # noqa: F401  (trace_for kept for symmetry with other tools)

VERDICTS = ("sound", "weak", "illogical")
TAGS = (
    "ignored_private_knowledge", "ignored_public_evidence", "unsupported_accusation",
    "factual_error", "contradicts_own_statements", "bandwagon_without_reason", "reasonable", "other",
)

RUBRIC = """You are a strict but fair referee for a game of Mafia played by AI players. You are given a full record of one game, including every player's secret role and private reasoning.

Rules in brief: town (villagers, one doctor, one detective) wins by ejecting all mafia. Each night the mafia kill one player. The doctor protects one player, and a protected player survives a kill. The detective checks one player and learns whether they are mafia. Each day everyone talks, then votes in secret. The player with the most votes is ejected and their role is revealed. A ejected or killed player's role becomes public. The mafia never target their own partner. If the doctor protects X and nobody dies that night, the mafia must have targeted X, so X is not mafia.

Rate every decision marked [D#] as one of:
- sound: a competent player holding ONLY that player's information could reasonably decide this. Mafia deceiving the town is sound if it serves their team. A guess made with no information (for example the first night) is sound.
- weak: defensible, but it rests on thin evidence or overlooks a clue that player had.
- illogical: it contradicts something that player knew or that was public, or it rests on a false statement of fact.

Rules for judging:
1. Judge the decision against what that player knew at that moment (public events plus their own private knowledge). Never judge by who turned out to be mafia.
2. A correct guess made for a bad reason is still weak or illogical. A wrong guess made for a good reason is sound.
3. Look at each decision's private reasoning, but judge the decision, not the writing style.
4. Be consistent. Do not give every decision the same verdict.
5. A vote that rests only on how someone talked (defensive, quiet, deflecting, joining a bandwagon) with no fact behind it is weak. On the first day that is often the best a player can do, but it is still thin evidence. Reserve sound for decisions backed by something concrete: a claim, a vote record, a night result, a contradiction, or the player's own private knowledge.
6. Use illogical only for a real contradiction or a false fact, not for thin evidence.

Answer with ONLY a JSON object, no other text:
{"decisions": [{"id": "D1", "verdict": "sound|weak|illogical", "tag": "<one of: ignored_private_knowledge, ignored_public_evidence, unsupported_accusation, factual_error, contradicts_own_statements, bandwagon_without_reason, reasonable, other>", "why": "one sentence of at most 25 words"}], "game": {"overall": <1 to 5, how logical the town's reasoning was across the game>, "summary": "two sentences"}}
Include every [D#] exactly once."""


def build_casebook(events: list[dict]) -> tuple[str, list[dict]]:
    """Turn a game log into text for the judge, and the list of decisions to be rated."""
    setup = next((e for e in events if e["kind"] == "setup"), None)
    if not setup:
        raise ValueError("log has no setup event, cannot build a casebook")
    roles: dict[str, str] = setup["data"]["roles"]
    mafia = [n for n, r in roles.items() if r == "mafia"]
    alive = set(roles)
    L = ["PLAYERS AND SECRET ROLES: " + ", ".join(f"{n} ({r})" for n, r in roles.items()), ""]
    decisions: list[dict] = []
    last_thought: dict[str, str] = {}
    checks: dict[str, list[str]] = {}
    protections: dict[str, list[str]] = {}
    quiet: set[int] = set()
    saved_on: dict[int, str] = {}

    def add(kind: str, player: str, text: str, day: int, target: str | None, reason: str, knowledge: str):
        did = f"D{len(decisions) + 1}"
        decisions.append({"id": did, "kind": kind, "player": player, "role": roles.get(player, "mafia"), "day": day,
                          "target": target, "reason": reason})
        L.append(f"[{did}] {text}")
        if reason:
            L.append(f"     {player}'s private reasoning: {reason}")
        if knowledge:
            L.append(f"     What {player} privately knows: {knowledge}")

    for ev in events:
        k, d, day = ev["kind"], ev.get("data", {}), ev.get("day", 0)
        if k == "phase":
            L.append(f"\n=== {ev['phase'].upper()} {day} ===")
        elif k == "thought":
            last_thought[d["speaker"]] = d.get("thought", "")
        elif k == "kill_decision":
            reason = " / ".join(last_thought.get(m, "") for m in mafia if m in alive and last_thought.get(m))
            add("mafia kill", " & ".join(m for m in mafia if m in alive) or "the mafia", f"The mafia choose to kill {d['target']}.",
                day, d["target"], reason, "they are the mafia and know each other")
        elif k == "save":
            a = d["actor"]
            known = "; ".join(protections.get(a, [])) or "nothing yet"
            add("protect", a, f"{a} (doctor) protects {d['target']}.", day, d["target"], last_thought.get(a, ""),
                f"their earlier protections and what followed: {known}")
            saved_on[day] = d["target"]
            protections.setdefault(a, []).append(f"night {day}: protected {d['target']}")
        elif k == "investigate":
            a = d["actor"]
            known = "; ".join(checks.get(a, [])) or "no checks yet"
            add("check", a, f"{a} (detective) investigates {d['target']} and learns: {d['result']}.", day, d["target"],
                last_thought.get(a, ""), f"their earlier checks: {known}")
            checks.setdefault(a, []).append(f"{d['target']} is {d['result']}")
        elif k == "no_death":
            quiet.add(day)
            L.append("Nobody died last night.")
            for a, plist in protections.items():
                if plist and plist[-1].startswith(f"night {day}:"):
                    plist[-1] += " (nobody died that night)"
        elif k == "death":
            alive.discard(d["victim"])
            how = "was killed in the night" if d.get("cause") == "night" else "was voted out"
            L.append(f"{d['victim']} {how}. They were {d['role']}.")
        elif k == "no_lynch":
            L.append("The vote was tied or empty. Nobody was ejected.")
        elif k == "speech":
            L.append(f"{d['speaker']} ({roles[d['speaker']]}) says: {d['message']}")
        elif k == "vote":
            if d["target"] is None:
                L.append(f"{d['voter']} abstains.")
                continue
            v = d["voter"]
            parts = []
            if roles[v] == "detective" and checks.get(v):
                parts.append("their checks: " + "; ".join(checks[v]))
            if roles[v] == "doctor" and protections.get(v):
                parts.append("their protections: " + "; ".join(protections[v]))
            if roles[v] == "mafia":
                parts.append("they are mafia; partner(s): " + (", ".join(m for m in mafia if m != v) or "none"))
            add("vote", v, f"{v} ({roles[v]}) votes to eject {d['target']}.", day, d["target"], last_thought.get(v, ""), "; ".join(parts))
        elif k == "end":
            L.append(f"\nGAME OVER: {d['winner']} wins.")
    return "\n".join(L), decisions


def parse_judgement(text: str, decisions: list[dict]) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    ids = {d["id"] for d in decisions}
    rows = []
    for r in obj.get("decisions", []):
        if r.get("id") in ids and r.get("verdict") in VERDICTS:
            tag = r.get("tag") if r.get("tag") in TAGS else "other"
            rows.append({"id": r["id"], "verdict": r["verdict"], "tag": tag, "why": str(r.get("why", ""))[:240]})
    if not rows:
        return None
    game = obj.get("game") or {}
    overall = game.get("overall") if isinstance(game.get("overall"), (int, float)) and 1 <= game["overall"] <= 5 else None
    return {"decisions": rows, "overall": overall, "summary": str(game.get("summary", ""))[:400]}


MIN_COVERAGE = 0.9  # a reply that rates fewer than this share of the decisions is treated as unusable


def judge_game(events: list[dict], client, max_tokens: int = 16000) -> dict:
    """Rate one game. Returns the casebook decisions joined with the judge's verdicts.

    The token budget is large because thinking models spend part of it on hidden reasoning, and a reply
    cut off in the middle of the JSON is useless. A retry changes the prompt, so the response cache
    cannot hand back the same bad reply.
    """
    casebook, decisions = build_casebook(events)
    parsed = None
    for attempt in range(3):
        ask = "\n\nRate every decision now."
        if attempt:
            ask = ("\n\nYour previous reply was cut off or was not valid JSON. Rate every decision again, keep every "
                   "'why' very short, and reply with ONLY the JSON object.")
        messages = [{"role": "system", "content": RUBRIC}, {"role": "user", "content": casebook + ask}]
        parsed = parse_judgement(client.chat(messages, max_tokens=max_tokens, temperature=0.0), decisions)
        if parsed and len(parsed["decisions"]) >= MIN_COVERAGE * len(decisions):
            break
        parsed = None
    if not parsed:
        return {"ok": False, "decisions": [], "overall": None, "summary": ""}
    from .logic import logic_game  # the hard checks act as an answer key for the votes they can settle

    hard = logic_game(events)
    bad = {(v["day"], v["voter"], v["target"]) for v in hard["violations"]}
    fine = {(v["day"], v["voter"], v["target"]) for v in hard["good"]}
    by_id = {d["id"]: d for d in decisions}
    rows = []
    for r in parsed["decisions"]:
        d = by_id[r["id"]]
        key = None
        if d["kind"] == "vote":
            sig = (d["day"], d["player"], d["target"])
            key = "violation" if sig in bad else "good" if sig in fine else None
        rows.append({**d, **r, "key": key})
    return {"ok": True, "overall": parsed["overall"], "summary": parsed["summary"], "decisions": rows, "decisions_total": len(decisions)}


def judge_batch(summary_path: str | Path, client, out_path: str | Path, log_dir: str | Path | None = None, progress=print,
                max_games: int | None = None) -> dict:
    """Judge the finished games of a batch, in seed order. Saves after each game and resumes from the output file.

    max_games limits the run to the first N seeds. Free tiers allow few requests for the stronger models, and
    judging the same seeds in every batch keeps the batches comparable.
    """
    summary_path, out_path = Path(summary_path), Path(out_path)
    batch = json.loads(summary_path.read_text(encoding="utf-8"))
    log_dir = Path(log_dir) if log_dir else summary_path.parent
    data = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"model": getattr(client, "model", "?"), "games": {}}
    finished = sorted((r for r in batch["results"] if r["status"] == "finished"), key=lambda r: r["seed"])
    for r in finished[:max_games]:
        if data["games"].get(r["game_id"], {}).get("ok"):
            continue
        res = judge_game(load_events(log_dir / f"{r['game_id']}.jsonl"), client)
        data["games"][r["game_id"]] = res
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        counts = Counter(d["verdict"] for d in res["decisions"])
        progress(f"{r['game_id']}: {'ok' if res['ok'] else 'FAILED'}  {dict(counts)}  overall {res['overall']}")
    return data


def compare_judges(a: dict, b: dict) -> dict:
    """How much two judges agree on the decisions both rated.

    Agreement on sound versus not sound is also given as Cohen's kappa, which discounts the agreement two
    judges would reach by chance (0 is chance, 1 is perfect).
    """
    pairs = []
    scores = []
    for gid, ga in a["games"].items():
        gb = b["games"].get(gid)
        if not (ga.get("ok") and gb and gb.get("ok")):
            continue
        da, db = {d["id"]: d for d in ga["decisions"]}, {d["id"]: d for d in gb["decisions"]}
        for did in sorted(da.keys() & db.keys(), key=lambda x: int(x[1:])):
            pairs.append((gid, did, da[did], db[did]))
        if ga.get("overall") is not None and gb.get("overall") is not None:
            scores.append(abs(ga["overall"] - gb["overall"]))
    n = len(pairs)
    exact = sum(1 for _, _, x, y in pairs if x["verdict"] == y["verdict"])
    ns_a = [x["verdict"] != "sound" for _, _, x, y in pairs]
    ns_b = [y["verdict"] != "sound" for _, _, x, y in pairs]
    po = sum(1 for p, q in zip(ns_a, ns_b) if p == q) / n if n else None
    pa, pb = (sum(ns_a) / n, sum(ns_b) / n) if n else (0, 0)
    pe = pa * pb + (1 - pa) * (1 - pb)
    kappa = round((po - pe) / (1 - pe), 2) if n and pe < 1 else None
    ill_either = [(g, i, x, y) for g, i, x, y in pairs if "illogical" in (x["verdict"], y["verdict"])]
    return {
        "games": len({g for g, _, _, _ in pairs}), "decisions": n,
        "exact_pct": round(100 * exact / n, 1) if n else None,
        "sound_vs_not_pct": round(100 * po, 1) if n else None,
        "kappa_sound_vs_not": kappa,
        "illogical_either": len(ill_either),
        "illogical_both": sum(1 for _, _, x, y in ill_either if x["verdict"] == y["verdict"] == "illogical"),
        "overall_score_mean_abs_diff": round(sum(scores) / len(scores), 2) if scores else None,
        "flat_disagreements": [
            {"game": g, "id": i, "player": x["player"], "role": x["role"], "kind": x["kind"], "day": x["day"],
             "a": x["verdict"], "a_why": x["why"], "b": y["verdict"], "b_why": y["why"]}
            for g, i, x, y in pairs if {x["verdict"], y["verdict"]} == {"sound", "illogical"}
        ][:8],
    }


def summarize_judgements(data: dict) -> dict:
    rows = [d for g in data["games"].values() if g.get("ok") for d in g["decisions"]]
    total = len(rows)

    def share(sel):
        part = [d for d in rows if sel(d)]
        c = Counter(d["verdict"] for d in part)
        n = len(part)
        return {"n": n, **{v: (round(100 * c[v] / n, 1) if n else None) for v in VERDICTS}}

    overall = [g["overall"] for g in data["games"].values() if g.get("ok") and g.get("overall") is not None]
    tags = Counter(d["tag"] for d in rows if d["verdict"] != "sound")
    bad = [d for d in rows if d.get("key") == "violation"]
    good = [d for d in rows if d.get("key") == "good"]
    answer_key = {
        "violations": len(bad),
        "violations_flagged": sum(1 for d in bad if d["verdict"] != "sound"),
        "violations_illogical": sum(1 for d in bad if d["verdict"] == "illogical"),
        "good_acts": len(good),
        "good_acts_sound": sum(1 for d in good if d["verdict"] == "sound"),
    }
    return {
        "answer_key": answer_key,
        "model": data.get("model"),
        "games": sum(1 for g in data["games"].values() if g.get("ok")),
        "failed": sum(1 for g in data["games"].values() if not g.get("ok")),
        "decisions": total,
        "all": share(lambda d: True),
        "by_kind": {k: share(lambda d, k=k: d["kind"] == k) for k in ("vote", "protect", "check", "mafia kill")},
        "by_role": {r: share(lambda d, r=r: d["role"] == r) for r in ("villager", "doctor", "detective", "mafia")},
        "overall_mean": round(sum(overall) / len(overall), 2) if overall else None,
        "tags": dict(tags.most_common()),
        "examples": [
            {"game": gid, **d} for gid, g in data["games"].items() if g.get("ok") for d in g["decisions"] if d["verdict"] == "illogical"
        ][:12],
    }
