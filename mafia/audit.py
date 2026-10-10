from __future__ import annotations

import json
import re
from pathlib import Path

from .analysis import load_events, trace_for

NAME_RE = re.compile(r"Your name is (\w+)\.")
ROLE_RE = re.compile(r"Your name is \w+\. You are (?:a |the )?(VILLAGER|MAFIA|DOCTOR|DETECTIVE)")
TEAMMATES_RE = re.compile(r"Your fellow mafia: ([^.]+)\.")
HISTORY_RE = re.compile(r"Game so far:\n(.*?)\n\nIt is ", re.S)


def audit_game(events: list[dict], trace_path: str | Path | None) -> dict:
    """Check every saved prompt of a game against what each player was allowed to know.

    For each prompt, every line of game history must be an event whose audience includes that player.
    The stated role must match the real role, and the teammate list must match the real mafia.
    """
    setup = next((e for e in events if e["kind"] == "setup"), None)
    if not setup or not trace_path:
        return {"calls": 0, "history_lines": 0, "leaks": [], "role_mismatches": 0, "teammate_mismatches": 0, "skipped": True}
    roles: dict[str, str] = setup["data"]["roles"]
    mafia = sorted(n for n, r in roles.items() if r == "mafia")

    allowed: dict[str, set[str]] = {n: set() for n in roles}
    for e in events:
        if e["kind"] == "setup":
            continue  # visible to nobody, by design
        line = f"[{e['phase']} {e['day']}] {e['text']}"
        for n in roles:
            if e["visible_to"] is None or n in e["visible_to"]:
                allowed[n].add(line)

    out = {"calls": 0, "history_lines": 0, "leaks": [], "role_mismatches": 0, "teammate_mismatches": 0, "skipped": False}
    for raw in Path(trace_path).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            break
        system, user = row["messages"][0]["content"], row["messages"][-1]["content"]
        who = NAME_RE.search(system)
        if not who or who.group(1) not in roles:
            continue
        me = who.group(1)
        out["calls"] += 1
        stated = ROLE_RE.search(system)
        if not stated or stated.group(1).lower() != roles[me]:
            out["role_mismatches"] += 1
        mates = TEAMMATES_RE.search(system)
        expected = [m for m in mafia if m != me] if roles[me] == "mafia" else []
        got = sorted(x.strip() for x in mates.group(1).split(",")) if mates else []
        if got != sorted(expected):
            out["teammate_mismatches"] += 1
        hist = HISTORY_RE.search(user)
        for line in (hist.group(1).splitlines() if hist else []):
            if line.startswith("(nothing has happened"):
                continue
            out["history_lines"] += 1
            if line not in allowed[me]:
                out["leaks"].append({"player": me, "role": roles[me], "line": line[:200]})
    return out


def audit_batch(summary_path: str | Path, log_dir: str | Path | None = None) -> dict:
    summary_path = Path(summary_path)
    batch = json.loads(summary_path.read_text(encoding="utf-8"))
    log_dir = Path(log_dir) if log_dir else summary_path.parent
    totals = {"games": 0, "skipped": 0, "calls": 0, "history_lines": 0, "leaks": [], "role_mismatches": 0, "teammate_mismatches": 0}
    for r in batch["results"]:
        if r["status"] != "finished":
            continue
        res = audit_game(load_events(log_dir / f"{r['game_id']}.jsonl"), trace_for(log_dir, r["game_id"]))
        if res["skipped"]:
            totals["skipped"] += 1
            continue
        totals["games"] += 1
        for k in ("calls", "history_lines", "role_mismatches", "teammate_mismatches"):
            totals[k] += res[k]
        totals["leaks"] += [{**x, "game": r["game_id"]} for x in res["leaks"]]
    return totals
