from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path

POWER = ("doctor", "detective")

# ---- text patterns (heuristics, tuned to be conservative) -------------------
CLAIM = {
    "doctor": re.compile(
        r"\b(i am|i'm|i’m|as|i was) (the |a |our )?doctor\b|\bmy (protection|save)\b|\bi (protected|saved)\b", re.I
    ),
    "detective": re.compile(
        r"\b(i am|i'm|i’m|as|i was) (the |a |our )?detective\b|\bmy (investigation|investigations|check|results?)\b"
        r"|\bi (investigated|checked)\b",
        re.I,
    ),
}
MAFIA_CONFESSION = re.compile(
    r"\b(we|us) mafia\b|\bi am (the |a |one of the )?(mafia|scum)\b|\bas (the |a )?mafia\b|\bfellow mafia\b"
    r"|\bmy (mafia )?partner\b|\bour (mafia )?(team|kill)\b",
    re.I,
)
FORMAT_LEAK = re.compile(r"^\s*\[|\(thinks\)|\"say\"\s*:|\"thought\"\s*:|^\s*\{|__invalid__|mafia channel|\bnight \d\]", re.I)
HALLUCINATED_HISTORY = re.compile(r"\b(yesterday|last round|last game|previous (game|round|day)|earlier game|day 0)\b", re.I)
SYCOPHANCY = re.compile(
    r"\b(good|great|fair|valid|solid|excellent|strong|important) point\b|\bi (completely |totally |fully )?agree\b"
    r"|\bexactly right\b|\byou'?re (absolutely )?right\b|\bmakes? (a lot of |perfect )?sense\b",
    re.I,
)


QUOTED = re.compile(r'"[^"]{4,}?"|“[^”]{4,}?”|(?<![\w])\'[^\']{6,}?\'(?![\w])')


def strip_quotes(text: str) -> str:
    """Drop quoted passages, so a villager quoting someone's claim is not counted as making it."""
    return QUOTED.sub(" ", text)


def load_events(path: str | Path) -> list[dict]:
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return events


OPTIONS_RE = re.compile(r"Choose who (?:the )?([a-z ]+?)(?: tonight)?\. Options: ([^.]+)\.")
TARGET_RE = re.compile(r'"target"\s*:\s*"([^"]+)"')


def trace_for(log_dir: str | Path, game_id: str) -> Path | None:
    """The prompt trace of a game. It is named by the second the game started, give or take a second."""
    try:
        ts = int(game_id.split("_")[1])
    except (IndexError, ValueError):
        return None
    for t in (ts, ts - 1, ts + 1, ts - 2, ts + 2):
        p = Path(log_dir) / f"trace_{t}.jsonl"
        if p.exists():
            return p
    return None


def prompt_position(trace_path: str | Path | None) -> Counter:
    """How often the model chose the name listed first in the prompt, from the saved prompts."""
    c: Counter = Counter()
    if not trace_path:
        return c
    for line in Path(trace_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            break
        m = OPTIONS_RE.search(row["messages"][-1]["content"])
        t = TARGET_RE.search(row["response"])
        if not m or not t:
            continue
        verb = m.group(1)
        cat = "kill" if "kills" in verb else "save" if "protect" in verb else "check" if "investigate" in verb else "vote" if "vote" in verb else None
        shown = [x.strip() for x in m.group(2).split(",")]
        if not cat or t.group(1) not in shown:
            continue
        c[f"ppos_n_{cat}"] += 1
        c[f"ppos_first_{cat}"] += shown[0] == t.group(1)
        c[f"ppos_exp_{cat}"] += round(1000 / len(shown))
    return c


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def analyze_game(events: list[dict], game_id: str = "", trace_path: str | Path | None = None) -> dict:
    """Score one game log. Returns counters plus a few quoted examples for the report."""
    setup = next((e for e in events if e["kind"] == "setup"), None)
    if not setup:
        raise ValueError("log has no setup event, cannot analyze")
    roles: dict[str, str] = setup["data"]["roles"]
    order = list(setup["data"].get("players") or roles)  # the order names are listed to the model
    mafia = {n for n, r in roles.items() if r == "mafia"}
    alive = set(roles)
    c: Counter = Counter(prompt_position(trace_path))

    def position(cat: str, options: list[str], chosen: str | None) -> None:
        """Record whether the model picked the first name it was shown, against the 1 in N chance."""
        if chosen is None or chosen not in options:
            return
        c[f"pos_n_{cat}"] += 1
        c[f"pos_first_{cat}"] += options[0] == chosen
        c[f"pos_exp_{cat}"] += round(1000 / len(options))

    def alive_list() -> list[str]:
        return [n for n in order if n in alive]
    ex: dict[str, list] = {k: [] for k in ("power_claims", "fake_claims", "confessions", "format", "history", "sycophancy", "dups")}

    def note(kind: str, ev: dict, text: str):
        if len(ex[kind]) < 6:
            ex[kind].append({"game": game_id, "day": ev["day"], "who": ev["data"].get("speaker", ""), "role": roles.get(ev["data"].get("speaker", ""), ""), "text": text})

    speeches: list[tuple[dict, str]] = []
    save_by_night: dict[int, dict] = {}
    kill_by_night: dict[int, str] = {}
    det_finds: list[dict] = []  # detective results that named a mafia
    det_speeches: list[tuple[int, str]] = []
    prev_save_target = None
    last_saved_target = None  # the target the doctor blocked last night, if any
    outed = set()
    winner = None
    deaths = 0

    for ev in events:
        k, d = ev["kind"], ev.get("data", {})
        if k == "speech":
            spk, msg = d["speaker"], d["message"]
            role = roles.get(spk, "")
            speeches.append((ev, msg))
            c["speeches"] += 1
            c["speech_chars"] += len(msg)
            if len(msg) < 25:
                c["short_speeches"] += 1
            if msg.strip() == "(says nothing)":
                c["fallback_speeches"] += 1
            if FORMAT_LEAK.search(msg):
                c["format_leaks"] += 1
                note("format", ev, msg)
            if ev["day"] == 1 and HALLUCINATED_HISTORY.search(msg):
                c["hallucinated_history"] += 1
                note("history", ev, msg)
            if SYCOPHANCY.search(msg[:140]):
                c["sycophantic"] += 1
                note("sycophancy", ev, msg)
            own = strip_quotes(msg)
            for prole, pat in CLAIM.items():
                if pat.search(own):
                    if role == prole:
                        c[f"{prole}_self_claim_speeches"] += 1
                        outed.add(prole)
                        note("power_claims", ev, msg)
                    elif role in ("mafia", "villager"):
                        c["fake_power_claims"] += 1
                        note("fake_claims", ev, msg)
            if role == "mafia" and MAFIA_CONFESSION.search(own):
                c["mafia_confessions"] += 1
                note("confessions", ev, msg)
            if role == "detective":
                det_speeches.append((ev["day"], msg))
        elif k == "thought":
            c["thoughts"] += 1
            c["thought_chars"] += len(d.get("thought", ""))
        elif k == "vote":
            voter, target = d["voter"], d["target"]
            position("vote", [n for n in alive_list() if n != voter], target)
            if voter in mafia:
                c["mafia_votes"] += 1
                if target in mafia:
                    c["mafia_votes_on_partner"] += 1
            else:
                c["town_votes"] += 1
                if target is None:
                    c["town_abstain"] += 1
                else:
                    if target in mafia:
                        c["town_votes_on_mafia"] += 1
                    m_alive = len(mafia & alive)
                    c["town_baseline_x1000"] += round(1000 * m_alive / max(1, len(alive) - 1))
        elif k == "death":
            victim = d["victim"]
            alive.discard(victim)
            deaths += 1
            if d.get("cause") == "vote":
                c["lynches"] += 1
                if d["role"] == "mafia":
                    c["lynch_mafia"] += 1
                else:
                    c["lynch_town"] += 1
                    if d["role"] in POWER:
                        c["lynch_power"] += 1
        elif k == "no_lynch":
            c["no_lynch"] += 1
        elif k == "kill_split":
            c["kill_splits"] += 1
        elif k == "kill_decision":
            c["night_kills"] += 1
            position("kill", [n for n in alive_list() if n not in mafia], d["target"])
            kill_by_night[ev["day"]] = d["target"]
            if roles.get(d["target"]) in POWER:
                c["kills_on_power"] += 1
            if d["target"] == last_saved_target:
                c["mafia_repeat_after_save"] += 1
            last_saved_target = None
        elif k == "save":
            c["doctor_saves"] += 1
            position("save", alive_list(), d["target"])
            save_by_night[ev["day"]] = d
            if d["target"] == d["actor"]:
                c["doctor_self_protect"] += 1
            if prev_save_target == d["target"]:
                c["doctor_repeat_target"] += 1
            prev_save_target = d["target"]
        elif k == "investigate":
            c["detective_checks"] += 1
            position("check", [n for n in alive_list() if n != d["actor"]], d["target"])
            if d["result"] == "MAFIA":
                det_finds.append({"day": ev["day"], "target": d["target"], "actor": d["actor"]})
        elif k == "no_death":
            n = ev["day"]
            if n in kill_by_night and save_by_night.get(n, {}).get("target") == kill_by_night[n]:
                c["kills_saved"] += 1
                last_saved_target = kill_by_night[n]
        elif k == "end":
            winner = d["winner"]

    # detective follow through
    for f in det_finds:
        c["detective_found_mafia"] += 1
        later = [(dd, m) for dd, m in det_speeches if dd >= f["day"] and re.search(rf"\b{re.escape(f['target'])}\b", m)]
        if later:
            c["detective_reported"] += 1
        else:
            c["detective_never_reported"] += 1

    # near duplicate speeches
    sets = [set(words(m)) for _, m in speeches]
    in_dup = set()
    pairs = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            if len(sets[i]) >= 8 and len(sets[j]) >= 8:
                s = jaccard(sets[i], sets[j])
                if s >= 0.6:
                    in_dup.update((i, j))
                    pairs.append((s, i, j))
    c["near_duplicate_speeches"] = len(in_dup)
    for s, i, j in sorted(pairs, reverse=True)[:3]:
        ex["dups"].append({"game": game_id, "score": round(s, 2), "a": f"{speeches[i][0]['data']['speaker']}: {speeches[i][1]}", "b": f"{speeches[j][0]['data']['speaker']}: {speeches[j][1]}"})

    # lexical variety
    bigrams = []
    for _, m in speeches:
        w = words(m)
        bigrams += list(zip(w, w[1:]))
    distinct2 = len(set(bigrams)) / len(bigrams) if bigrams else 0.0
    openers = Counter(" ".join(words(m)[:3]) for _, m in speeches if words(m))
    top_opener_share = (openers.most_common(1)[0][1] / len(speeches)) if speeches else 0.0

    roles_alive_end = {r: any(roles[n] == r and n in alive for n in roles) for r in POWER}
    from .logic import logic_game  # imported here because logic.py itself imports from this module

    return {
        "logic": logic_game(events),
        "game": game_id,
        "winner": winner,
        "days": max((e.get("day", 0) for e in events), default=0),
        "deaths": deaths,
        "counts": dict(c),
        "distinct2": round(distinct2, 3),
        "top_opener_share": round(top_opener_share, 3),
        "outed": sorted(outed),
        "power_alive_end": roles_alive_end,
        "examples": ex,
    }


# ---- aggregation --------------------------------------------------------------
def _sum(games: list[dict], key: str) -> int:
    return sum(g["counts"].get(key, 0) for g in games)


def _pct(num: float, den: float) -> float:
    return round(100 * num / den, 1) if den else 0.0


def aggregate(games: list[dict], results: list[dict]) -> dict:
    n = len(games)
    sp = _sum(games, "speeches")
    tv = _sum(games, "town_votes")
    voted = tv - _sum(games, "town_abstain")
    baseline = _sum(games, "town_baseline_x1000") / 1000
    day_fig = [g["days"] for g in games]
    det_found = _sum(games, "detective_found_mafia")
    kills = _sum(games, "night_kills")
    from .logic import logic_rates  # imported here because logic.py itself imports from this module

    return {
        "logic": logic_rates(games),
        "games": n,
        "town_wins": sum(1 for g in games if g["winner"] == "town"),
        "mafia_wins": sum(1 for g in games if g["winner"] == "mafia"),
        "avg_days": round(statistics.mean(day_fig), 2) if day_fig else 0,
        "invalid_actions": sum(r["invalid_actions"] for r in results),
        "llm_errors": sum(r["llm_errors"] for r in results),
        "calls": sum(r["calls"] for r in results),
        "tokens": sum(r["prompt_tokens"] + r["completion_tokens"] for r in results),
        "minutes": round(sum(r["seconds"] for r in results) / 60, 1),
        "speeches": sp,
        "avg_speech_chars": round(_sum(games, "speech_chars") / sp, 1) if sp else 0,
        "short_speech_pct": _pct(_sum(games, "short_speeches"), sp),
        "fallback_speeches": _sum(games, "fallback_speeches"),
        "format_leaks": _sum(games, "format_leaks"),
        "hallucinated_history": _sum(games, "hallucinated_history"),
        "sycophancy_pct": _pct(_sum(games, "sycophantic"), sp),
        "near_duplicate_pct": _pct(_sum(games, "near_duplicate_speeches"), sp),
        "distinct2_mean": round(statistics.mean(g["distinct2"] for g in games), 3) if games else 0,
        "top_opener_share_mean": round(statistics.mean(g["top_opener_share"] for g in games), 3) if games else 0,
        "doctor_self_claim_speeches": _sum(games, "doctor_self_claim_speeches"),
        "detective_self_claim_speeches": _sum(games, "detective_self_claim_speeches"),
        "games_doctor_outed": sum(1 for g in games if "doctor" in g["outed"]),
        "games_detective_claimed": sum(1 for g in games if "detective" in g["outed"]),
        "fake_power_claims": _sum(games, "fake_power_claims"),
        "mafia_confessions": _sum(games, "mafia_confessions"),
        "town_vote_accuracy_pct": _pct(_sum(games, "town_votes_on_mafia"), voted),
        "town_vote_random_baseline_pct": _pct(baseline, voted),
        "town_abstain_pct": _pct(_sum(games, "town_abstain"), tv),
        "mafia_votes_on_partner": _sum(games, "mafia_votes_on_partner"),
        "lynches": _sum(games, "lynches"),
        "lynch_mafia": _sum(games, "lynch_mafia"),
        "lynch_power": _sum(games, "lynch_power"),
        "no_lynch": _sum(games, "no_lynch"),
        "night_kills": kills,
        "kills_on_power_pct": _pct(_sum(games, "kills_on_power"), kills),
        "kills_saved": _sum(games, "kills_saved"),
        "doctor_saves": _sum(games, "doctor_saves"),
        "doctor_self_protect_pct": _pct(_sum(games, "doctor_self_protect"), _sum(games, "doctor_saves")),
        "doctor_repeat_target": _sum(games, "doctor_repeat_target"),
        "mafia_repeat_after_save": _sum(games, "mafia_repeat_after_save"),
        "detective_found_mafia": det_found,
        "detective_reported_pct": _pct(_sum(games, "detective_reported"), det_found),
        "kill_splits": _sum(games, "kill_splits"),
        # "first_pct" is the earliest seat (the first name in the roster) picked. "prompt_first_pct" is the name that was
        # listed first in the prompt. Each is compared with the rate expected from pure chance.
        "position": {
            cat: {
                "n": _sum(games, f"pos_n_{cat}"),
                "first_pct": _pct(_sum(games, f"pos_first_{cat}"), _sum(games, f"pos_n_{cat}")),
                "chance_pct": round(_sum(games, f"pos_exp_{cat}") / 10 / max(1, _sum(games, f"pos_n_{cat}")), 1),
                "prompt_n": _sum(games, f"ppos_n_{cat}"),
                "prompt_first_pct": _pct(_sum(games, f"ppos_first_{cat}"), _sum(games, f"ppos_n_{cat}")),
                "prompt_chance_pct": round(_sum(games, f"ppos_exp_{cat}") / 10 / max(1, _sum(games, f"ppos_n_{cat}")), 1),
            }
            for cat in ("kill", "save", "check", "vote")
        },
    }


def analyze_batch(summary_path: str | Path, log_dir: str | Path | None = None) -> tuple[dict, list[dict]]:
    summary_path = Path(summary_path)
    batch = json.loads(summary_path.read_text(encoding="utf-8"))
    log_dir = Path(log_dir) if log_dir else summary_path.parent
    games = []
    for r in batch["results"]:
        if r["status"] != "finished":
            continue
        games.append(analyze_game(load_events(log_dir / f"{r['game_id']}.jsonl"), r["game_id"], trace_for(log_dir, r["game_id"])))
    return batch, games


# ---- comparing two batches ------------------------------------------------------
def _finished(batch: dict) -> list[dict]:
    return [r for r in batch["results"] if r["status"] == "finished"]


def render_comparison(name_a: str, batch_a: dict, games_a: list[dict], name_b: str, batch_b: dict, games_b: list[dict],
                      judge_a: dict | None = None, judge_b: dict | None = None) -> str:
    a = aggregate(games_a, _finished(batch_a))
    b = aggregate(games_b, _finished(batch_b))

    def per_game(x, key):
        return round(x[key] / max(1, x["games"]), 1)

    def pos(x, cat):
        p = x["position"][cat]
        return f"{p['first_pct']}% of {p['n']}"

    def lf(num, den, x, _unused=None):
        return f"{x['logic'][num]} of {x['logic'][den]}"

    def ppos(x, cat):
        p = x["position"][cat]
        return f"{p['prompt_first_pct']}% of {p['prompt_n']}" if p["prompt_n"] else "no trace"

    rows = [
        ("Games finished", a["games"], b["games"], ""),
        ("Doctor voted for provably town", lf("doctor_voted_saved_target", "doctor_vote_opportunities", a), lf("doctor_voted_saved_target", "doctor_vote_opportunities", b), "Should be 0."),
        ("Detective voted for a cleared player", lf("detective_voted_cleared", "detective_vote_opportunities", a), lf("detective_voted_cleared", "detective_vote_opportunities", b), "Should be 0."),
        ("Detective voted for a found mafia", lf("detective_voted_found_mafia", "detective_found_vote_opportunities", a), lf("detective_voted_found_mafia", "detective_found_vote_opportunities", b), "Higher is better."),
        ("False statements about the record", f"{a['logic']['fact_false']} of {a['logic']['fact_total']}", f"{b['logic']['fact_false']} of {b['logic']['fact_total']}", "Lower is better."),
        ("Vote reasoning names the target", f"{a['logic']['reason_names_target_pct']}%", f"{b['logic']['reason_names_target_pct']}%", ""),
        ("Votes resting on concrete evidence", f"{a['logic']['basis_concrete_pct']}%", f"{b['logic']['basis_concrete_pct']}%", ""),
        ("Votes resting on nothing specific", f"{a['logic']['basis_none_pct']}%", f"{b['logic']['basis_none_pct']}%", "Lower is better."),
        ("Town followed a false detective claim", lf("claim_false_believed", "claim_false_total", a, "claim"), lf("claim_false_believed", "claim_false_total", b, "claim"), "Lower is better."),
        ("Town wins (not a quality measure)", a["town_wins"], b["town_wins"], ""),
        ("Average days", a["avg_days"], b["avg_days"], ""),
        ("Invalid actions", a["invalid_actions"], b["invalid_actions"], "Should stay at 0."),
        ("API errors", a["llm_errors"], b["llm_errors"], ""),
        ("Model calls per game", per_game(a, "calls"), per_game(b, "calls"), ""),
        ("Tokens per game", f"{a['tokens'] / max(1, a['games']):,.0f}", f"{b['tokens'] / max(1, b['games']):,.0f}", ""),
        ("Detective check: first listed in prompt", ppos(a, "check"), ppos(b, "check"), f"Chance is about {a['position']['check']['prompt_chance_pct'] or a['position']['check']['chance_pct']}%."),
        ("Mafia kill: first listed in prompt", ppos(a, "kill"), ppos(b, "kill"), f"Chance is about {a['position']['kill']['prompt_chance_pct'] or a['position']['kill']['chance_pct']}%."),
        ("Doctor protection: first listed in prompt", ppos(a, "save"), ppos(b, "save"), f"Chance is about {a['position']['save']['prompt_chance_pct'] or a['position']['save']['chance_pct']}%."),
        ("Day vote: first listed in prompt", ppos(a, "vote"), ppos(b, "vote"), f"Chance is about {a['position']['vote']['prompt_chance_pct'] or a['position']['vote']['chance_pct']}%."),
        ("Detective check: earliest seat", pos(a, "check"), pos(b, "check"), f"Chance is about {a['position']['check']['chance_pct']}%."),
        ("Mafia kill: earliest seat", pos(a, "kill"), pos(b, "kill"), f"Chance is about {a['position']['kill']['chance_pct']}%."),
        ("Doctor protection: earliest seat", pos(a, "save"), pos(b, "save"), f"Chance is about {a['position']['save']['chance_pct']}%."),
        ("Day vote: earliest seat", pos(a, "vote"), pos(b, "vote"), f"Chance is about {a['position']['vote']['chance_pct']}%."),
        ("Town vote accuracy", f"{a['town_vote_accuracy_pct']}%", f"{b['town_vote_accuracy_pct']}%", "Random guessing scores about 27%."),
        ("Ejections that hit mafia", f"{a['lynch_mafia']} of {a['lynches']}", f"{b['lynch_mafia']} of {b['lynches']}", ""),
        ("Power roles ejected by town", a["lynch_power"], b["lynch_power"], ""),
        ("Mafia kills aimed at power roles", f"{a['kills_on_power_pct']}%", f"{b['kills_on_power_pct']}%", "Chance is 40% with 6 players."),
        ("Kills stopped by the doctor", f"{a['kills_saved']} of {a['night_kills']}", f"{b['kills_saved']} of {b['night_kills']}", ""),
        ("Detective found a mafia", a["detective_found_mafia"], b["detective_found_mafia"], ""),
        ("Games where the doctor outed themself", a["games_doctor_outed"], b["games_doctor_outed"], ""),
        ("Agree with the last speaker", f"{a['sycophancy_pct']}%", f"{b['sycophancy_pct']}%", ""),
        ("Near duplicate speeches", f"{a['near_duplicate_pct']}%", f"{b['near_duplicate_pct']}%", ""),
        ("Format leaks", a["format_leaks"], b["format_leaks"], "Should stay at 0."),
    ]
    L = [f"# Comparison: {name_a} against {name_b}\n", f"| Metric | {name_a} | {name_b} | Note |", "| --- | --- | --- | --- |"]
    L += [f"| {m} | {x} | {y} | {n} |" for m, x, y, n in rows]
    if judge_a and judge_b:
        def p(x):
            return "n/a" if x is None else f"{x}%"

        L += [f"\n## Judge review (same seeds, same judge)\n",
              f"Rated by `{judge_a['model']}` and `{judge_b['model']}`. Only the games both batches had judged are comparable, "
              f"so check the game counts: {judge_a['games']} against {judge_b['games']}.\n",
              f"| Metric | {name_a} | {name_b} | Note |", "| --- | --- | --- | --- |",
              f"| Games judged | {judge_a['games']} | {judge_b['games']} | |",
              f"| Decisions rated | {judge_a['decisions']} | {judge_b['decisions']} | |",
              f"| Sound | {p(judge_a['all']['sound'])} | {p(judge_b['all']['sound'])} | Higher is better. |",
              f"| Weak | {p(judge_a['all']['weak'])} | {p(judge_b['all']['weak'])} | Thin evidence or an overlooked clue. |",
              f"| Illogical | {p(judge_a['all']['illogical'])} | {p(judge_b['all']['illogical'])} | Lower is better. |",
              f"| Day votes rated sound | {p(judge_a['by_kind']['vote']['sound'])} | {p(judge_b['by_kind']['vote']['sound'])} | |",
              f"| Villager decisions rated sound | {p(judge_a['by_role']['villager']['sound'])} | {p(judge_b['by_role']['villager']['sound'])} | |",
              f"| Game logic score, 1 to 5 | {judge_a['overall_mean']} | {judge_b['overall_mean']} | |"]

    wa = {r["seed"]: r for r in _finished(batch_a)}
    wb = {r["seed"]: r for r in _finished(batch_b)}
    seeds = sorted(set(wa) & set(wb))
    if seeds:
        same = sum(1 for s in seeds if wa[s]["winner"] == wb[s]["winner"])
        L += [f"\n## Same seeds, same roles\n", f"{same} of {len(seeds)} seeds ended with the same winner.\n",
              f"| Seed | {name_a} winner | {name_b} winner | {name_a} days | {name_b} days |", "| --- | --- | --- | --- | --- |"]
        L += [f"| {s} | {wa[s]['winner']} | {wb[s]['winner']} | {wa[s]['days']} | {wb[s]['days']} |" for s in seeds]
    return "\n".join(L) + "\n"


# ---- report -------------------------------------------------------------------
def render_judge_section(js: dict) -> list[str]:
    """Lines for the report from mafia.judge.summarize_judgements output."""
    def pct(x):
        return "n/a" if x is None else f"{x}%"

    def row(label, s):
        return f"| {label} | {s['n']} | {pct(s['sound'])} | {pct(s['weak'])} | {pct(s['illogical'])} |"

    L = [f"\n## Judge review\n",
         f"{js['decisions']} decisions in {js['games']} games were rated by `{js['model']}` ({js['failed']} games could not be rated). "
         "The judge saw every secret role and private reasoning, but rated each decision only against what that player knew at the time. "
         "Sound means a competent player could reasonably decide this. Weak means thin evidence or an overlooked clue. "
         "Illogical means it contradicts something the player knew or a false fact.\n",
         "| Decisions | Count | Sound | Weak | Illogical |", "| --- | --- | --- | --- | --- |", row("All", js["all"])]
    L += [row(k.capitalize(), s) for k, s in js["by_kind"].items() if s["n"]]
    L += [row(f"By role: {r}", s) for r, s in js["by_role"].items() if s["n"]]
    L.append(f"\nOverall logic of the game, scored 1 to 5 by the judge: **{js['overall_mean']}** on average.\n")
    k = js.get("answer_key") or {}
    if k.get("violations") or k.get("good_acts"):
        L.append("**Checking the judge against the hard checks.** These votes can be settled mechanically, so they act as an answer key:\n")
        if k.get("violations"):
            L.append(f"* Votes that contradicted what the voter knew: the judge rated {k['violations_flagged']} of {k['violations']} as weak or illogical "
                     f"({k['violations_illogical']} as illogical).")
        if k.get("good_acts"):
            L.append(f"* Votes where the detective acted on a mafia they had found: the judge rated {k['good_acts_sound']} of {k['good_acts']} as sound.")
    if js["tags"]:
        L.append("\nWhy decisions were not rated sound: " + ", ".join(f"{t.replace('_', ' ')} ({n})" for t, n in js["tags"].items()) + ".")
    if js["examples"]:
        L.append("\n### Decisions the judge rated illogical\n")
        for x in js["examples"]:
            L.append(f"* game {x['game'][-6:]} day {x['day']}, {x['player']} ({x['role']}), {x['kind']} {x.get('target')}: {x['why']}")
    return L


def render_report(batch: dict, games: list[dict], audit: dict | None = None, judge: dict | None = None) -> str:
    results = [r for r in batch["results"] if r["status"] == "finished"]
    a = aggregate(games, results)
    cfg = batch["config"]
    L: list[str] = []
    L.append(f"# Batch quality report\n")
    L.append(f"{a['games']} finished games, {cfg['players']} players, model `{cfg['model']}`, seeds from {cfg['seed_start']}.\n")

    L.append("## Games\n")
    L.append("| Seed | Winner | Days | Calls | Tokens | Invalid | Minutes | Power roles alive at end |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    by_id = {g["game"]: g for g in games}
    for r in sorted(results, key=lambda x: x["seed"]):
        g = by_id.get(r["game_id"], {})
        alive = ", ".join(k for k, v in g.get("power_alive_end", {}).items() if v) or "none"
        L.append(f"| {r['seed']} | {r['winner']} | {r['days']} | {r['calls']} | {r['prompt_tokens'] + r['completion_tokens']:,} | {r['invalid_actions']} | {r['seconds'] / 60:.1f} | {alive} |")

    def table(title: str, rows: list[tuple[str, str, str]]):
        L.append(f"\n## {title}\n")
        L.append("| Metric | Value | How to read it |")
        L.append("| --- | --- | --- |")
        for m, v, note in rows:
            L.append(f"| {m} | {v} | {note} |")

    table("Reliability and cost", [
        ("Games finished", f"{a['games']} of {cfg['games']}", "Failed games are excluded from everything below."),
        ("Invalid actions", str(a["invalid_actions"]), "Replies the engine could not use. It retried, then used a safe default."),
        ("API errors", str(a["llm_errors"]), "Failed model calls."),
        ("Fallback speeches", str(a["fallback_speeches"]), "Times a player said nothing because every retry failed."),
        ("Model calls per game", f"{a['calls'] / max(1, a['games']):.1f}", "Free tier budget per game."),
        ("Tokens per game", f"{a['tokens'] / max(1, a['games']):,.0f}", "Prompt plus reply tokens."),
        ("Minutes per game", f"{a['minutes'] / max(1, a['games']):.1f}", "At the configured request rate."),
    ])
    if audit is not None:
        table("Information leak audit", [
            ("Games audited", f"{audit['games']} ({audit['skipped']} skipped, no prompt trace)", "Needs the saved prompts in trace files."),
            ("Prompts checked", f"{audit['calls']:,}", "Every prompt sent to a player."),
            ("History lines checked", f"{audit['history_lines']:,}", "Each must be an event that player was allowed to see."),
            ("Leaks", str(len(audit["leaks"])), "A line of history the player should not have seen. Must be 0."),
            ("Role mismatches", str(audit["role_mismatches"]), "The role in the prompt differs from the real role. Must be 0."),
            ("Teammate mismatches", str(audit["teammate_mismatches"]), "The fellow mafia list is wrong. Must be 0."),
        ])
    lg = a["logic"]

    def frac(num, den):
        return f"{num} of {den}" if den else "no chances"

    table("Reasoning quality (hard checks)", [
        ("Doctor voted for a player their own protection had shown to be town", frac(lg["doctor_voted_saved_target"], lg["doctor_vote_opportunities"]),
         "A blocked kill means the mafia aimed at that player, so they cannot be mafia. Voting them out ignores what the doctor knows. Should be 0."),
        ("Detective voted for a player they had cleared", frac(lg["detective_voted_cleared"], lg["detective_vote_opportunities"]),
         "Ignoring their own result. Should be 0."),
        ("Detective voted for a mafia they had found", frac(lg["detective_voted_found_mafia"], lg["detective_found_vote_opportunities"]),
         "Acting on their own result. Higher is better."),
        ("Mafia voted for their own partner", frac(lg["mafia_voted_partner"], lg["mafia_votes"]), "Rarely a good idea."),
        ("Statements about the public record that were false", f"{frac(lg['fact_false'], lg['fact_total'])} ({lg['fact_false_pct']}%)" if lg["fact_total"] else "none to check",
         "Claims about who voted for whom, who died and how, who claimed a role, or who a dead player was. Mafia lying about themselves is not counted."),
        ("Vote reasoning names the player voted for", f"{lg['reason_names_target_pct']}% of {lg['vote_reasons']}" if lg["vote_reasons"] else "n/a",
         "Whether the private reasoning behind a vote is about the person actually voted for."),
        ("What votes rest on: a claim, a vote record, a night result, or an inconsistency", f"{lg['basis_concrete_pct']}%", "Concrete evidence cited in the reasoning."),
        ("What votes rest on: behavior only", f"{lg['basis_behavior_only_pct']}%", "Defensive, evasive, quiet, and similar. Weaker, but all there is on day 1."),
        ("What votes rest on: nothing specific", f"{lg['basis_none_pct']}%", "No reason that points at anything."),
        ("Town followed a true detective claim", frac(lg["claim_true_believed"], lg["claim_true_total"]), "A true claim should get more votes on the accused than on the claimant."),
        ("Town followed a false detective claim", frac(lg["claim_false_believed"], lg["claim_false_total"]), "A false claim (mafia counterclaim, or invented result) that the town believed. Lower is better."),
    ])
    if judge is not None:
        L.extend(render_judge_section(judge))
    table("Outcomes (not a quality measure)", [
        ("Town wins", f"{a['town_wins']} of {a['games']}", "A win can come from bad reasoning and a loss from good reasoning. Small sample."),
        ("Mafia wins", f"{a['mafia_wins']} of {a['games']}", ""),
        ("Average days", str(a["avg_days"]), "Very short games mean luck decided them."),
        ("Ejections that hit mafia", f"{a['lynch_mafia']} of {a['lynches']}", "How often the daily vote found the mafia."),
        ("Power roles ejected by town", str(a["lynch_power"]), "Town voting out its own doctor or detective."),
        ("Days with no ejection", str(a["no_lynch"]), "Ties or all abstentions."),
    ])
    table("Deduction and voting", [
        ("Town vote accuracy", f"{a['town_vote_accuracy_pct']}%", "Share of town votes that targeted a mafia player."),
        ("Random guessing baseline", f"{a['town_vote_random_baseline_pct']}%", "What random voting would score in the same situations. Accuracy above this means real deduction."),
        ("Town abstentions", f"{a['town_abstain_pct']}%", "Votes cast for nobody."),
        ("Mafia votes for their own partner", str(a["mafia_votes_on_partner"]), "Bussing. Usually a strategic sacrifice or a mistake."),
    ])
    table("Role play and information control", [
        ("Games where the doctor outed themself", f"{a['games_doctor_outed']} of {a['games']}", "Public speech that reveals the protection. Ideally rare and deliberate."),
        ("Games where the detective claimed", f"{a['games_detective_claimed']} of {a['games']}", "Detective speech that reveals investigations."),
        ("Fake power role claims", str(a["fake_power_claims"]), "Speeches by mafia or villagers claiming to be the doctor or detective."),
        ("Mafia speaking as mafia in public", str(a["mafia_confessions"]), "Should be near zero. Flagged phrases may include accusations, so read the examples."),
        ("Detective found a mafia", str(a["detective_found_mafia"]), ""),
        ("Detective reported it later", f"{a['detective_reported_pct']}%", "Named the found mafia in a later public speech. Low means the result was wasted."),
        ("Mafia kills aimed at power roles", f"{a['kills_on_power_pct']}%", "Random targeting would hit a power role 2 in 5 times with 6 players."),
        ("Kills stopped by the doctor", f"{a['kills_saved']} of {a['night_kills']}", ""),
        ("Doctor protected themself", f"{a['doctor_self_protect_pct']}%", ""),
        ("Doctor repeated the same target", str(a["doctor_repeat_target"]), "Nights the doctor picked the same person as the night before."),
        ("Mafia retried a saved target", str(a["mafia_repeat_after_save"]), "Nights the mafia hit the same person right after being blocked."),
        ("Mafia disagreements on the target", str(a["kill_splits"]), "Rounds of kill voting that split."),
    ])
    pos = a["position"]
    label = {"kill": "Mafia kill target", "save": "Doctor protection", "check": "Detective check", "vote": "Day vote"}
    rows = []
    for c, p in pos.items():
        if p["prompt_n"]:
            rows.append((f"{label[c]}: first name listed in the prompt", f"{p['prompt_first_pct']}% of {p['prompt_n']} (chance {p['prompt_chance_pct']}%)",
                         "Far above chance means the model leans on list position. Needs the saved prompt trace." if c == "kill" else ""))
        rows.append((f"{label[c]}: earliest seat (first in the roster)", f"{p['first_pct']}% of {p['n']} (chance {p['chance_pct']}%)",
                     "Far above chance means a preference for certain names, whatever the list order." if c == "kill" else ""))
    table("Choice bias", rows)
    table("Writing quality", [
        ("Average speech length", f"{a['avg_speech_chars']} characters", ""),
        ("Very short speeches", f"{a['short_speech_pct']}%", "Under 25 characters."),
        ("Agree with the last speaker", f"{a['sycophancy_pct']}%", "Speeches with phrases like good point or I agree. High means players echo each other."),
        ("Near duplicate speeches", f"{a['near_duplicate_pct']}%", "Share of speeches that are 60 percent or more similar to another in the same game."),
        ("Word pair variety", str(a["distinct2_mean"]), "Distinct two word pairs over all pairs. Closer to 1 is more varied."),
        ("Most common opening", f"{round(100 * a['top_opener_share_mean'], 1)}%", "Share of speeches starting with the same three words."),
        ("Format leaks", str(a["format_leaks"]), "Speeches showing JSON or log tags. Should be zero."),
        ("Invented history on day 1", str(a["hallucinated_history"]), "Speeches on day 1 that mention yesterday or earlier rounds."),
    ])

    def section(title: str, key: str, fmt):
        items = [x for g in games for x in g["examples"][key]][:6]
        if not items:
            return
        L.append(f"\n### {title}\n")
        for x in items:
            L.append(fmt(x))

    L.append("\n## Logic problems found\n")
    logic_titles = [
        ("doctor_vote", "Doctor ignored what their protection showed"),
        ("detective_vote", "Detective ignored their own result"),
        ("false_fact", "Statements the public record contradicts"),
        ("reason_mismatch", "Reasoning about one player, vote for another"),
        ("claim", "How the town handled detective claims"),
    ]
    any_logic = False
    for key, title in logic_titles:
        items = [(g["game"], x) for g in games for x in g["logic"]["examples"][key]][:5]
        if items:
            any_logic = True
            L.append(f"\n### {title}\n")
            for gid, x in items:
                L.append(f"* game {gid[-6:]} day {x['day']}, {x['who']} ({x['role']}): {x['text']}")
    if not any_logic:
        L.append("None found.")

    L.append("\n## Examples\n")
    line = lambda x: f"* game {x['game'][-6:]} day {x['day']}, {x['who']} ({x['role']}): \"{x['text'][:240]}\""
    section("Power role claims by the real holder", "power_claims", line)
    section("Fake power role claims", "fake_claims", line)
    section("Mafia speaking as mafia", "confessions", line)
    section("Format leaks", "format", line)
    section("Invented history", "history", line)
    section("Agreeing with the last speaker", "sycophancy", line)
    dups = [x for g in games for x in g["examples"]["dups"]]
    if dups:
        L.append("\n### Near duplicate pairs\n")
        for x in sorted(dups, key=lambda y: -y["score"])[:4]:
            L.append(f"* game {x['game'][-6:]}, similarity {x['score']}:\n  * {x['a'][:200]}\n  * {x['b'][:200]}")
    return "\n".join(L) + "\n"
