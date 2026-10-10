from __future__ import annotations

import argparse
import json
import sys

from mafia.judge import compare_judges


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="How much do two judges agree on the same games?")
    ap.add_argument("first", help="verdicts from one judge, for example logs/judge36_batch_shuffle.json")
    ap.add_argument("second", help="verdicts from another judge")
    a = ap.parse_args()
    one, two = (json.load(open(p, encoding="utf-8")) for p in (a.first, a.second))
    r = compare_judges(one, two)
    print(f"{one.get('model')} against {two.get('model')}: {r['games']} games, {r['decisions']} decisions rated by both")
    print(f"  same verdict: {r['exact_pct']}%   sound versus not sound: {r['sound_vs_not_pct']}%   kappa: {r['kappa_sound_vs_not']}")
    print(f"  illogical by either judge: {r['illogical_either']}, by both: {r['illogical_both']}   mean gap in the 1 to 5 game score: {r['overall_score_mean_abs_diff']}")
    for x in r["flat_disagreements"]:
        print(f"  DISAGREE game {x['game'][-6:]} {x['id']} day {x['day']} {x['player']} ({x['role']}) {x['kind']}: {x['a']} ({x['a_why']}) versus {x['b']} ({x['b_why']})")


if __name__ == "__main__":
    main()
