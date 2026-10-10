from __future__ import annotations

import argparse
import sys

from mafia.batch import run_batch
from mafia.setup import DEFAULT_MODEL, SetupError, load_env


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    ap = argparse.ArgumentParser(description="Play a batch of games with consecutive seeds.")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--mafia", type=int, default=None, help="override mafia count")
    ap.add_argument("--seed-start", type=int, default=100)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--rpm", type=float, default=10, help="requests per minute cap")
    ap.add_argument("--random", action="store_true", help="free random players, no API calls")
    ap.add_argument("--no-cache", action="store_true", help="do not replay saved replies (use for replicates of the same seeds)")
    ap.add_argument("--summary", default=None, help="summary file to create, or to resume from")
    ap.add_argument("--log-dir", default="logs")
    a = ap.parse_args()
    try:
        data = run_batch(
            a.games, players=a.players, seed_start=a.seed_start, mafia=a.mafia, model=a.model,
            rpm=a.rpm, log_dir=a.log_dir, use_random=a.random, summary_path=a.summary, cache=not a.no_cache,
        )
    except SetupError as e:
        sys.exit(str(e))
    done = [r for r in data["results"] if r["status"] == "finished"]
    print(f"\nFinished {len(done)} of {a.games} games. Summary: {data['summary_path']}")


if __name__ == "__main__":
    main()
