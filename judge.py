from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mafia.judge import judge_batch, summarize_judgements
from mafia.llm.client import ChatClient
from mafia.setup import SetupError, load_env


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    ap = argparse.ArgumentParser(description="Have a judge model rate every key decision in a batch of games.")
    ap.add_argument("summary", help="batch summary file, for example logs/batch_shuffle.json")
    ap.add_argument("--model", default="gemini-3.5-flash", help="judge model (use a different one than the players)")
    ap.add_argument("--rpm", type=float, default=10)
    ap.add_argument("--max-games", type=int, default=None, help="judge only the first N seeds (stronger models have small free quotas)")
    ap.add_argument("--out", default=None, help="where to save the verdicts (default: logs/judge_<batch>.json)")
    a = ap.parse_args()
    out = Path(a.out) if a.out else Path(a.summary).with_name("judge_" + Path(a.summary).stem + ".json")
    client = ChatClient(model=a.model, rpm=a.rpm)
    if not client.api_key:
        sys.exit(str(SetupError("Set GEMINI_API_KEY first.")))
    try:
        data = judge_batch(a.summary, client, out, max_games=a.max_games)
    except RuntimeError as e:  # for example a daily quota error
        sys.exit(f"Stopped: {e}\nRerun the same command to resume.")
    s = summarize_judgements(data)
    print(f"\n{s['games']} games, {s['decisions']} decisions rated by {s['model']}. Saved to {out}")
    print(f"verdicts: {s['all']}   overall logic score (1 to 5): {s['overall_mean']}")


if __name__ == "__main__":
    main()
