from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mafia.analysis import analyze_batch, render_comparison, render_report
from mafia.audit import audit_batch
from mafia.judge import summarize_judgements


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Score the quality of a batch of games.")
    ap.add_argument("summary", help="batch summary file, for example logs/batch_main.json")
    ap.add_argument("--log-dir", default=None, help="folder with the game logs (default: next to the summary)")
    ap.add_argument("--out", default=None, help="where to write the markdown report")
    ap.add_argument("--baseline", default=None, help="an earlier batch summary to compare against")
    ap.add_argument("--baseline-judge", default=None, help="judge verdicts for the baseline batch, for the judged comparison")
    ap.add_argument("--judge", default=None, help="judge verdicts to include (default: logs/judge_<summary name>.json if it exists)")
    a = ap.parse_args()
    batch, games = analyze_batch(a.summary, a.log_dir)
    judge_file = Path(a.judge) if a.judge else Path(a.summary).with_name("judge_" + Path(a.summary).stem + ".json")
    judged = summarize_judgements(json.loads(judge_file.read_text(encoding="utf-8"))) if judge_file.exists() else None
    report = render_report(batch, games, audit_batch(a.summary, a.log_dir), judged)
    out = Path(a.out) if a.out else Path(a.summary).with_name(Path(a.summary).stem + "_report.md")
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written to {out}")
    if a.baseline:
        base_batch, base_games = analyze_batch(a.baseline, a.log_dir)
        base_judge = Path(a.baseline_judge) if a.baseline_judge else None
        base_judged = summarize_judgements(json.loads(base_judge.read_text(encoding="utf-8"))) if base_judge and base_judge.exists() else None
        comparison = render_comparison(Path(a.baseline).stem, base_batch, base_games, Path(a.summary).stem, batch, games, base_judged, judged)
        cmp_out = out.with_name(Path(a.summary).stem + "_vs_" + Path(a.baseline).stem + ".md")
        cmp_out.write_text(comparison, encoding="utf-8")
        print(comparison)
        print(f"Comparison written to {cmp_out}")


if __name__ == "__main__":
    main()
