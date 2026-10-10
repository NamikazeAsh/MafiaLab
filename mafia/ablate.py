"""Replay real prompts with one instruction changed, to test whether a change fixes a specific mistake.

A batch of games is too slow and too noisy to test a rare mistake: the doctor voted out a player their own
protection had proved was town in 2 of 19 votes. Instead this takes the real prompts from the saved traces
where that situation arose, asks the model again many times with and without the change, and compares. The
situation is identical in both arms, so any difference comes from the instruction.
"""
from __future__ import annotations

import json
import re
from math import comb, sqrt
from pathlib import Path

from .agents.base import VOTE, Request
from .agents.llm_agent import INVALID, extract_reason, parse_target
from .analysis import OPTIONS_RE, load_events, trace_for
from .audit import HISTORY_RE, NAME_RE, ROLE_RE

DOCTOR_HINT = (
    "Hard fact for the doctor: if you protected someone and nobody died that night, the mafia must have "
    "aimed at that player, so that player is NOT mafia. Never vote for such a player. Treat them as confirmed town."
)


VILLAGER_HINT = (
    "Before you vote, find the strongest concrete fact in the game so far that points at your target: something a "
    "player did or said that can be checked, such as a vote, a claim, a contradiction, or who died or did not die. "
    "Name that fact in your reason. If there is no such fact yet, say so, and pick the player whose behavior fits "
    "being town the least. Never invent a fact."
)


def with_hint(messages: list[dict], hint: str) -> list[dict]:
    """The same messages with extra text added to the end of the system prompt."""
    out = [dict(m) for m in messages]
    out[0]["content"] = out[0]["content"] + "\n\n" + hint
    return out


def doctor_vote_cases(summary_paths: list[str | Path], models: set[str] | None = None, log_dir: str | Path | None = None) -> list[dict]:
    """Real doctor day votes where the doctor's own protection had shown a living player to be town.

    The situation is read from the prompt itself, so it holds exactly what the doctor could see: a line
    "You protect X" on a night, and "Nobody died last night" on the day after, with X still alive.
    """
    cases = []
    for sp in map(Path, summary_paths):
        batch = json.loads(sp.read_text(encoding="utf-8"))
        if models and batch["config"]["model"] not in models:
            continue
        ldir = Path(log_dir) if log_dir else sp.parent
        for r in batch["results"]:
            if r["status"] != "finished":
                continue
            tp = trace_for(ldir, r["game_id"])
            if not tp:
                continue
            roles = load_events(ldir / f"{r['game_id']}.jsonl")[0]["data"]["roles"]
            for raw in tp.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                row = json.loads(raw)
                system, user = row["messages"][0]["content"], row["messages"][-1]["content"]
                role = ROLE_RE.search(system)
                opts = OPTIONS_RE.search(user)
                hist = HISTORY_RE.search(user)
                if not (role and role.group(1) == "DOCTOR" and opts and "vote" in opts.group(1) and hist):
                    continue
                lines = hist.group(1).splitlines()
                quiet_days = {m.group(1) for ln in lines if (m := re.match(r"\[day (\d+)\] Nobody died last night\.", ln))}
                protected = [(m.group(1), m.group(2)) for ln in lines if (m := re.match(r"\[night (\d+)\] You protect (\w+)\.", ln))]
                options = [x.strip() for x in opts.group(2).split(",")]
                blocked = sorted({t for night, t in protected if night in quiet_days and t in options})
                if blocked:
                    cases.append({"game": r["game_id"], "player": NAME_RE.search(system).group(1), "messages": row["messages"],
                                  "options": options, "blocked": blocked, "mafia": sorted(n for n, x in roles.items() if x == "mafia"),
                                  "original_target": (re.search(r'"target"\s*:\s*"([^"]+)"', row["response"]) or [None, None])[1]})
    return cases


def villager_vote_cases(summary_paths: list[str | Path], models: set[str] | None = None, log_dir: str | Path | None = None,
                        max_cases: int | None = None, seed: int = 0) -> list[dict]:
    """Real villager day votes, for testing whether an instruction makes the stated reason better grounded."""
    import random

    cases = []
    for sp in map(Path, summary_paths):
        batch = json.loads(sp.read_text(encoding="utf-8"))
        if models and batch["config"]["model"] not in models:
            continue
        ldir = Path(log_dir) if log_dir else sp.parent
        for r in batch["results"]:
            tp = trace_for(ldir, r["game_id"]) if r["status"] == "finished" else None
            if not tp:
                continue
            roles = load_events(ldir / f"{r['game_id']}.jsonl")[0]["data"]["roles"]
            for raw in tp.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                row = json.loads(raw)
                system, user = row["messages"][0]["content"], row["messages"][-1]["content"]
                role, opts, hist = ROLE_RE.search(system), OPTIONS_RE.search(user), HISTORY_RE.search(user)
                if not (role and role.group(1) == "VILLAGER" and opts and "vote" in opts.group(1) and hist):
                    continue
                me = NAME_RE.search(system).group(1)
                options = [x.strip() for x in opts.group(2).split(",")]
                cases.append({"game": r["game_id"], "player": me, "messages": row["messages"], "options": options,
                              "mafia": sorted(n for n, x in roles.items() if x == "mafia"), "roster": sorted(set(options) | {me}),
                              "history": hist.group(1).splitlines()})
    if max_cases and len(cases) > max_cases:
        cases = random.Random(seed).sample(cases, max_cases)
    return cases


def unsupported_vote_claims(reason: str, history: list[str], roster: list[str]) -> int:
    """How many 'X voted for Y' statements in a reason are not in the game history the player was shown."""
    names = "|".join(sorted((re.escape(n) for n in roster), key=len, reverse=True))
    pattern = re.compile(rf"\b({names})\b (?:has |had |also )?(?:voted|votes) (?:for|against|to (?:eject|lynch|remove|kill)|out) (?:\w+ )?\b({names})\b", re.I)
    real = {(m.group(1).lower(), m.group(2).lower()) for ln in history if (m := re.search(rf"\] ({names}) votes for ({names})\.", ln, re.I))}
    return sum(1 for m in pattern.finditer(reason) if m.group(1).lower() != m.group(2).lower() and (m.group(1).lower(), m.group(2).lower()) not in real)


def score_villager_arm(cases: list[dict], rows: list[dict]) -> dict:
    from collections import Counter

    from .logic import CONCRETE, EVIDENCE

    c: Counter = Counter()
    for r in rows:
        case = cases[r["case"]]
        c["samples"] += 1
        if r["invalid"]:
            c["invalid"] += 1
            continue
        if r["target"] is None:
            c["abstained"] += 1
            continue
        c["votes"] += 1
        c["hit_mafia"] += r["target"] in case["mafia"]
        cats = {k for k, pat in EVIDENCE.items() if pat.search(r["reason"])}
        c["basis_concrete" if cats & set(CONCRETE) else "basis_behavior_only" if cats else "basis_none"] += 1
        c["invented_vote_record"] += unsupported_vote_claims(r["reason"], case["history"], case["roster"]) > 0
    return dict(c)


def compare_villager_arms(cases: list[dict], control: list[dict], treatment: list[dict]) -> dict:
    a, b = score_villager_arm(cases, control), score_villager_arm(cases, treatment)
    out = {"control": a, "treatment": b}
    for key in ("basis_concrete", "basis_none", "invented_vote_record", "hit_mafia"):
        ka, na, kb, nb = a.get(key, 0), a.get("votes", 0), b.get(key, 0), b.get("votes", 0)
        out[key] = {"control_pct": round(100 * ka / na, 1) if na else None, "treatment_pct": round(100 * kb / nb, 1) if nb else None,
                    "p": round(fisher_two_sided(ka, na - ka, kb, nb - kb), 4) if na and nb else None}
    return out


PAIR_PROMPT = """You are comparing two replies that a player in a game of Mafia gave when asked to vote. Both replies were written in the same situation, which is shown below exactly as the player saw it.

Decide which reply's reasoning is better grounded in what the player actually knew: a concrete, checkable fact from the game so far, correctly stated, beats a vague impression. A reply that states something that is not in the game history, or contradicts it, is worse. Do not prefer a reply because of its length, its tone, or which target it picked.

Answer with ONLY a JSON object: {"better": "A" or "B" or "tie", "a_invents_facts": true or false, "b_invents_facts": true or false, "why": "one sentence"}"""


def judge_pairs(cases: list[dict], data: dict, client, max_pairs: int, seed: int = 0, progress=print) -> list[dict]:
    """Blind pairwise comparison of the control reply and the hinted reply for the same prompt, order randomized."""
    import random

    rng = random.Random(seed)
    done = data.setdefault("pairs", {})
    for ci in sorted(data["control"], key=int)[:max_pairs]:
        if ci in done:
            continue
        ctl = [r for r in data["control"][ci] if not r["invalid"] and r["target"] is not None]
        trt = [r for r in data["treatment"][ci] if not r["invalid"] and r["target"] is not None]
        if not ctl or not trt:
            continue
        a_is_control = rng.random() < 0.5
        pick_c, pick_t = rng.choice(ctl), rng.choice(trt)
        first, second = (pick_c, pick_t) if a_is_control else (pick_t, pick_c)
        situation = "\n\n".join(m["content"] for m in cases[int(ci)]["messages"])
        text = (f"{PAIR_PROMPT}\n\n=== THE SITUATION ===\n{situation}\n\n=== REPLY A ===\nVote: {first['target']}\nReason: {first['reason']}\n\n"
                f"=== REPLY B ===\nVote: {second['target']}\nReason: {second['reason']}\n")
        reply = client.chat([{"role": "user", "content": text}], max_tokens=8000, temperature=0.0)
        m = re.search(r"\{.*\}", reply, re.S)
        try:
            obj = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            obj = {}
        if obj.get("better") not in ("A", "B", "tie"):
            continue
        winner = "tie" if obj["better"] == "tie" else ("control" if (obj["better"] == "A") == a_is_control else "hint")
        invents = {"control": bool(obj.get("a_invents_facts" if a_is_control else "b_invents_facts")),
                   "hint": bool(obj.get("b_invents_facts" if a_is_control else "a_invents_facts"))}
        done[ci] = {"winner": winner, "invents": invents, "why": str(obj.get("why", ""))[:300], "control_reason": pick_c["reason"], "hint_reason": pick_t["reason"]}
        progress(f"pair {len(done)}: {winner}")
    return list(done.values())


def summarize_pairs(pairs: list[dict]) -> dict:
    hint = sum(1 for p in pairs if p["winner"] == "hint")
    ctl = sum(1 for p in pairs if p["winner"] == "control")
    n = hint + ctl
    # a two sided sign test on the decisive pairs: under no difference each side wins half the time
    p = min(1.0, 2 * sum(comb(n, k) for k in range(0, min(hint, ctl) + 1)) / 2 ** n) if n else None
    return {"pairs": len(pairs), "hint_wins": hint, "control_wins": ctl, "ties": len(pairs) - n, "sign_test_p": round(p, 4) if p is not None else None,
            "control_invents": sum(1 for p_ in pairs if p_["invents"]["control"]), "hint_invents": sum(1 for p_ in pairs if p_["invents"]["hint"])}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Fisher's exact test for the table [[a, b], [c, d]]."""
    r1, c1, n = a + b, a + c, a + b + c + d
    pr = lambda x: comb(c1, x) * comb(n - c1, r1 - x) / comb(n, r1)
    obs = pr(a)
    return min(1.0, sum(pr(x) for x in range(max(0, r1 - (n - c1)), min(r1, c1) + 1) if pr(x) <= obs + 1e-12))


def run_case(case: dict, ci: int, client, variant, samples: int) -> list[dict]:
    """Ask one case `samples` times. `variant` turns the original messages into the ones to send."""
    req = Request(VOTE, tuple(case["options"]), allow_abstain=True)
    messages = variant(case["messages"])
    rows = []
    for s in range(samples):
        text = client.chat(messages, max_tokens=150, temperature=0.8)
        target = parse_target(text, req)
        rows.append({"case": ci, "sample": s, "target": None if target is INVALID else target, "invalid": target is INVALID,
                     "reason": extract_reason(text)})
    return rows


def run_arm(cases: list[dict], client, variant, samples: int) -> list[dict]:
    rows = []
    for ci, case in enumerate(cases):
        rows += run_case(case, ci, client, variant, samples)
    return rows


def run_experiment(cases: list[dict], client, hint: str, samples: int, out_path: str | Path, progress=print) -> dict:
    """Run the control and the hinted arm on every case, saving after each case so a quota stop can resume.

    The two arms alternate case by case, so any drift in the model over the run affects both equally.
    The client must have its response cache off, or repeated identical prompts would return one saved reply.
    """
    out_path = Path(out_path)
    data = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"hint": hint, "samples": samples, "control": {}, "treatment": {}}
    arms = (("control", lambda m: m), ("treatment", lambda m: with_hint(m, hint)))
    for ci, case in enumerate(cases):
        for name, variant in arms:
            if str(ci) in data[name]:
                continue
            data[name][str(ci)] = run_case(case, ci, client, variant, samples)
            out_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        extra = f", proven town {case['blocked']}" if "blocked" in case else ""
        progress(f"case {ci + 1}/{len(cases)} done ({case['game']}{extra})")
    return data


def with_user_note(messages: list[dict], note: str) -> list[dict]:
    """The same messages with a note added at the end of the last user message, right before the player answers."""
    out = [dict(m) for m in messages]
    out[-1]["content"] = out[-1]["content"] + "\n\n" + note
    return out


def doctor_note(case: dict) -> str:
    """The doctor's own conclusion, stated as a fact. It uses only what the doctor could see: their protections and the quiet nights."""
    names = " and ".join(case["blocked"])
    verb = "is" if len(case["blocked"]) == 1 else "are"
    return (f"Your own notes: you protected {names} on a night when nobody died, so the mafia must have aimed at "
            f"{'them' if len(case['blocked']) > 1 else 'that player'}. {names} {verb} NOT mafia.")


def run_extra_arm(cases: list[dict], client, data: dict, name: str, variant_for_case, samples: int, out_path: str | Path, progress=print) -> dict:
    """Add one more arm (for example a note instead of a hint) to saved results, saving after each case."""
    out_path = Path(out_path)
    arm = data.setdefault(name, {})
    for ci, case in enumerate(cases):
        if str(ci) in arm:
            continue
        arm[str(ci)] = run_case(case, ci, client, variant_for_case(case), samples)
        out_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        progress(f"{name}: case {ci + 1}/{len(cases)} done ({case['game']})")
    return data


def arm_rows(data: dict, name: str) -> list[dict]:
    return [r for ci in sorted(data[name], key=int) for r in data[name][ci]]


def score_arm(cases: list[dict], rows: list[dict]) -> dict:
    valid = [r for r in rows if not r["invalid"]]
    voted = [r for r in valid if r["target"] is not None]
    bad = [r for r in voted if r["target"] in cases[r["case"]]["blocked"]]
    hit = [r for r in voted if r["target"] in cases[r["case"]]["mafia"]]
    per_case = {}
    for r in voted:
        per_case.setdefault(r["case"], [0, 0])
        per_case[r["case"]][1] += 1
        per_case[r["case"]][0] += r["target"] in cases[r["case"]]["blocked"]
    return {"samples": len(rows), "invalid": len(rows) - len(valid), "abstained": len(valid) - len(voted), "votes": len(voted),
            "voted_proven_town": len(bad), "voted_mafia": len(hit),
            "per_case_rate": {c: (a / n if n else None) for c, (a, n) in per_case.items()}}


def compare_arms(cases: list[dict], control: list[dict], treatment: list[dict]) -> dict:
    a, b = score_arm(cases, control), score_arm(cases, treatment)
    p = fisher_two_sided(a["voted_proven_town"], a["votes"] - a["voted_proven_town"], b["voted_proven_town"], b["votes"] - b["voted_proven_town"])
    better = sum(1 for c in a["per_case_rate"] if a["per_case_rate"][c] is not None and b["per_case_rate"].get(c) is not None
                 and b["per_case_rate"][c] < a["per_case_rate"][c])
    worse = sum(1 for c in a["per_case_rate"] if a["per_case_rate"][c] is not None and b["per_case_rate"].get(c) is not None
                and b["per_case_rate"][c] > a["per_case_rate"][c])
    return {"control": a, "treatment": b, "fisher_p": round(p, 4),
            "control_ci": [round(100 * x, 1) for x in wilson(a["voted_proven_town"], a["votes"])],
            "treatment_ci": [round(100 * x, 1) for x in wilson(b["voted_proven_town"], b["votes"])],
            "cases_improved": better, "cases_worse": worse, "cases": len(cases)}
