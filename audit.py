from __future__ import annotations

import argparse
import sys

from mafia.audit import audit_batch


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Check saved prompts for information a player should not have seen.")
    ap.add_argument("summaries", nargs="+", help="batch summary files, for example logs/batch_main.json")
    a = ap.parse_args()
    bad = 0
    for path in a.summaries:
        r = audit_batch(path)
        print(f"{path}: {r['games']} games, {r['calls']} prompts, {r['history_lines']} history lines checked"
              f" ({r['skipped']} games skipped, no trace)")
        print(f"  leaks: {len(r['leaks'])}   role mismatches: {r['role_mismatches']}   teammate mismatches: {r['teammate_mismatches']}")
        for x in r["leaks"][:5]:
            print(f"  LEAK in {x['game']} to {x['player']} ({x['role']}): {x['line']}")
        bad += len(r["leaks"]) + r["role_mismatches"] + r["teammate_mismatches"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
