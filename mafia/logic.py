"""Hard checks on whether players reasoned consistently with what they knew.

Nothing here looks at who won. Each check asks whether a decision or a statement is consistent with
information the player had, or with the public record. The checks are conservative: they only count
cases that can be settled from the game log.
"""
from __future__ import annotations

import re
from collections import Counter

from .analysis import CLAIM, strip_quotes

# What a private reason for a vote rests on. A reason can cite several kinds, or none.
EVIDENCE = {
    "claim_or_result": re.compile(r"\b(claim\w*|detective|investigat\w*|result|checked|cleared|confirm\w*)\b", re.I),
    "voting_record": re.compile(r"\b(voted|voting|bandwagon\w*|lynch\w*|mislynch\w*|drove|driving|led the|charge|pushed for)\b", re.I),
    "night_outcome": re.compile(r"\b(no[- ]?kill|nobody died|no one died|killed|protect\w*|saved|doctor)\b", re.I),
    "inconsistency": re.compile(r"\b(flip\w*|inconsistent|contradict\w*|backtrack\w*|changed|earlier|previously|story|echo\w*)\b", re.I),
    "behavior": re.compile(
        r"\b(defensive|deflect\w*|evasive|dodg\w*|aggressive|quiet|silent|eager|pushing|manufactur\w*|pressure|"
        r"nervous|desperate|panic\w*|suspicious|too (safe|smooth|helpful|quick))\b", re.I),
}
CONCRETE = ("claim_or_result", "voting_record", "night_outcome", "inconsistency")


def _name_pattern(roster: list[str]) -> str:
    return "|".join(sorted((re.escape(n) for n in roster), key=len, reverse=True))


def logic_game(events: list[dict]) -> dict:
    """Return {'counts': Counter-like dict, 'examples': {...}} for one game."""
    setup = next((e for e in events if e["kind"] == "setup"), None)
    if not setup:
        raise ValueError("log has no setup event, cannot analyze")
    roles: dict[str, str] = setup["data"]["roles"]
    roster = list(roles)
    N = _name_pattern(roster)
    mafia = {n for n, r in roles.items() if r == "mafia"}
    det = next((n for n, r in roles.items() if r == "detective"), None)
    doc = next((n for n, r in roles.items() if r == "doctor"), None)

    VOTED = re.compile(rf"\b({N})\b (?:has |had |also )?(?:voted|votes) (?:for|against|to (?:eject|lynch|remove|kill)|out) (?:\w+ )?\b({N})\b", re.I)
    WAS_ROLE = re.compile(rf"\b({N})\b (?:was|turned out to be|had been) (?:the |a |an )?(detective|doctor|villager|mafia)\b", re.I)
    PERISHED = re.compile(rf"\b({N})\b (?:was|got|has been|were) (killed|eliminated|ejected|voted out|lynched)\b", re.I)
    NOBODY = re.compile(r"\b(nobody|no one|noone) (?:died|was killed|got killed)|\bno[- ]kill night\b", re.I)
    CLAIMED = re.compile(rf"\b({N})\b (?:claimed|claims|claimed to be|said (?:he|she|they) (?:was|is)) (?:to be )?(?:the |a )?(detective|doctor)\b", re.I)

    c: Counter = Counter()
    ex: dict[str, list] = {k: [] for k in ("doctor_vote", "detective_vote", "false_fact", "reason_mismatch", "claim")}
    violations: list[dict] = []   # votes the hard checks say contradicted what the voter knew
    good: list[dict] = []         # votes the hard checks say acted on what the voter knew

    def note(kind: str, day: int, who: str, text: str):
        if len(ex[kind]) < 5:
            ex[kind].append({"day": day, "who": who, "role": roles.get(who, ""), "text": text[:240]})

    alive = set(roles)
    dead: dict[str, dict] = {}
    votes_seen: list[tuple[int, str, str | None]] = []     # (day, voter, target)
    speeches_by: dict[str, list[str]] = {n: [] for n in roster}
    last_thought: dict[str, str] = {}
    kill_by_night: dict[int, str] = {}
    save_by_night: dict[int, dict] = {}
    blocked: set[str] = set()      # targets the doctor protected on a night when nobody died
    cleared: set[str] = set()      # players the detective checked and found not mafia
    found: set[str] = set()        # players the detective checked and found mafia
    night_death: dict[int, str] = {}
    quiet_night: set[int] = set()
    pending_claims: list[dict] = []
    day_votes: dict[int, list[tuple[str, str | None]]] = {}

    def close_day(day: int):
        """Judge how the town responded to detective claims made that day, once the votes are in."""
        for cl in [p for p in pending_claims if p["day"] == day]:
            pending_claims.remove(cl)
            others = [(v, t) for v, t in day_votes.get(day, []) if v not in (cl["claimant"], cl["accused"])]
            on_accused = sum(1 for _, t in others if t == cl["accused"])
            on_claimant = sum(1 for _, t in others if t == cl["claimant"])
            believed = on_accused > on_claimant
            key = "true" if cl["true"] else "false"
            c[f"claim_{key}_total"] += 1
            c[f"claim_{key}_believed"] += believed
            note("claim", day, cl["claimant"], f"{'true' if cl['true'] else 'false'} claim against {cl['accused']}: "
                 f"{on_accused} votes on the accused, {on_claimant} on the claimant")

    for ev in events:
        k, d, day = ev["kind"], ev.get("data", {}), ev.get("day", 0)
        if k == "thought":
            last_thought[d["speaker"]] = d.get("thought", "")
        elif k == "kill_decision":
            kill_by_night[day] = d["target"]
        elif k == "save":
            save_by_night[day] = d
        elif k == "investigate":
            (found if d["result"] == "MAFIA" else cleared).add(d["target"])
        elif k == "no_death":
            quiet_night.add(day)
            if day in kill_by_night and save_by_night.get(day, {}).get("target") == kill_by_night[day]:
                blocked.add(kill_by_night[day])   # the kill was aimed at this player, so they are not mafia
        elif k == "death":
            alive.discard(d["victim"])
            dead[d["victim"]] = {"day": day, "cause": d.get("cause"), "role": d["role"]}
            if d.get("cause") == "night":
                night_death[day] = d["victim"]
            else:
                close_day(day)
        elif k == "no_lynch":
            close_day(day)
        elif k == "speech":
            spk, msg = d["speaker"], d["message"]
            plain = strip_quotes(msg)
            speeches_by[spk].append(plain)
            # factual statements about the public record
            for m in VOTED.finditer(plain):
                a = next((n for n in roster if n.lower() == m.group(1).lower()), m.group(1))
                b = next((n for n in roster if n.lower() == m.group(2).lower()), m.group(2))
                if a == b:
                    continue
                true = any(v == a and t == b and vd < day for vd, v, t in votes_seen)
                c["fact_total"] += 1
                c["fact_vote_total"] += 1
                if not true:
                    c["fact_false"] += 1
                    c["fact_vote_false"] += 1
                    note("false_fact", day, spk, f"says {a} voted for {b}, which the record does not show: \"{msg[:160]}\"")
            for m in WAS_ROLE.finditer(plain):
                who = next((n for n in roster if n.lower() == m.group(1).lower()), None)
                role = m.group(2).lower()
                if who in dead:            # only a revealed role can be checked
                    c["fact_total"] += 1
                    if dead[who]["role"] != role:
                        c["fact_false"] += 1
                        note("false_fact", day, spk, f"says {who} was {role}, but they were {dead[who]['role']}: \"{msg[:160]}\"")
            for m in PERISHED.finditer(plain):
                who = next((n for n in roster if n.lower() == m.group(1).lower()), None)
                how = "night" if m.group(2).lower() == "killed" else "vote" if m.group(2).lower() in ("ejected", "voted out", "lynched") else None
                if who in dead and how:
                    c["fact_total"] += 1
                    if dead[who]["cause"] != how:
                        c["fact_false"] += 1
                        note("false_fact", day, spk, f"says {who} was {m.group(2)}, but the record says otherwise: \"{msg[:160]}\"")
            hypothetical = re.search(r"\b(if|unless|whether|when)\s+(nobody|no one|noone)\b", plain, re.I)
            if NOBODY.search(plain) and not hypothetical:
                c["fact_total"] += 1
                if day not in quiet_night:
                    c["fact_false"] += 1
                    note("false_fact", day, spk, f"says nobody died last night, but {night_death.get(day, 'someone')} did: \"{msg[:160]}\"")
            for m in CLAIMED.finditer(plain):
                who = next((n for n in roster if n.lower() == m.group(1).lower()), None)
                role = m.group(2).lower()
                if who and who != spk and who in roles:
                    c["fact_total"] += 1
                    if not any(CLAIM[role].search(s) for s in speeches_by[who]):
                        c["fact_false"] += 1
                        note("false_fact", day, spk, f"says {who} claimed to be the {role}, but they never did: \"{msg[:160]}\"")
            # a first person detective claim that names a mafia
            if CLAIM["detective"].search(plain) and re.search(r"\b(mafia|scum|guilty)\b", plain, re.I):
                named = [(m.start(), next(n for n in roster if n.lower() == m.group(0).lower()))
                         for m in re.finditer(rf"\b({N})\b", plain, re.I) if m.group(0).lower() != spk.lower()]
                accused, true = None, False
                if spk == det:
                    # the real detective makes a claim we can judge only by naming a mafia they really found
                    hits = [n for _, n in named if n in found]
                    if hits:
                        accused, true = hits[0], True
                elif named:
                    tokens = [m.start() for m in re.finditer(r"\b(mafia|scum|guilty)\b", plain, re.I)]
                    accused = min(named, key=lambda x: min(abs(x[0] - t) for t in tokens))[1]   # the name nearest the accusation
                if accused and not any(p["claimant"] == spk and p["accused"] == accused and p["day"] == day for p in pending_claims):
                    pending_claims.append({"day": day, "claimant": spk, "accused": accused, "true": true})
        elif k == "vote":
            voter, target = d["voter"], d["target"]
            votes_seen.append((day, voter, target))
            day_votes.setdefault(day, []).append((voter, target))
            reason = last_thought.get(voter, "")
            if target is not None and reason:
                c["vote_reasons"] += 1
                named = re.search(rf"\b{re.escape(target)}\b", reason, re.I) is not None   # players write names in any case
                c["vote_reason_names_target"] += named
                if not named:
                    note("reason_mismatch", day, voter, f"voted {target}, but the reasoning never mentions them: \"{reason[:160]}\"")
                cats = {name for name, pat in EVIDENCE.items() if pat.search(reason)}
                if cats & set(CONCRETE):
                    c["vote_basis_concrete"] += 1
                elif cats:
                    c["vote_basis_behavior_only"] += 1
                else:
                    c["vote_basis_none"] += 1
            if target is None:
                continue
            if voter == doc and blocked & alive:
                c["doctor_vote_opportunities"] += 1
                if target in blocked:
                    violations.append({"day": day, "voter": voter, "target": target})
                    c["doctor_voted_saved_target"] += 1
                    note("doctor_vote", day, voter, f"voted {target}, whom their own protection had just shown to be the mafia's target: \"{reason[:160]}\"")
            if voter == det:
                if cleared & alive:
                    c["detective_vote_opportunities"] += 1
                    if target in cleared:
                        violations.append({"day": day, "voter": voter, "target": target})
                        c["detective_voted_cleared"] += 1
                        note("detective_vote", day, voter, f"voted {target}, whom they had checked and cleared: \"{reason[:160]}\"")
                if found & alive:
                    c["detective_found_vote_opportunities"] += 1
                    if target in found:
                        good.append({"day": day, "voter": voter, "target": target})
                        c["detective_voted_found_mafia"] += 1
                    else:
                        violations.append({"day": day, "voter": voter, "target": target})
                        note("detective_vote", day, voter, f"voted {target} while a mafia they had found, {sorted(found & alive)[0]}, was alive: \"{reason[:160]}\"")
            if voter in mafia:
                c["mafia_votes"] += 1
                c["mafia_voted_partner"] += target in mafia
    # a vote can end the game before close_day sees a death or no_lynch event
    for day in sorted({p["day"] for p in pending_claims}):
        close_day(day)
    return {"counts": dict(c), "examples": ex, "violations": violations, "good": good}


def logic_rates(games: list[dict]) -> dict:
    """Sum the per game counts and turn them into rates for a batch report."""
    def s(key):
        return sum(g["logic"]["counts"].get(key, 0) for g in games)

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "doctor_vote_opportunities": s("doctor_vote_opportunities"),
        "doctor_voted_saved_target": s("doctor_voted_saved_target"),
        "detective_vote_opportunities": s("detective_vote_opportunities"),
        "detective_voted_cleared": s("detective_voted_cleared"),
        "detective_found_vote_opportunities": s("detective_found_vote_opportunities"),
        "detective_voted_found_mafia": s("detective_voted_found_mafia"),
        "mafia_votes": s("mafia_votes"),
        "mafia_voted_partner": s("mafia_voted_partner"),
        "fact_total": s("fact_total"),
        "fact_false": s("fact_false"),
        "fact_false_pct": pct(s("fact_false"), s("fact_total")),
        "vote_reasons": s("vote_reasons"),
        "reason_names_target_pct": pct(s("vote_reason_names_target"), s("vote_reasons")),
        "basis_concrete_pct": pct(s("vote_basis_concrete"), s("vote_reasons")),
        "basis_behavior_only_pct": pct(s("vote_basis_behavior_only"), s("vote_reasons")),
        "basis_none_pct": pct(s("vote_basis_none"), s("vote_reasons")),
        "claim_true_total": s("claim_true_total"),
        "claim_true_believed": s("claim_true_believed"),
        "claim_false_total": s("claim_false_total"),
        "claim_false_believed": s("claim_false_believed"),
    }
