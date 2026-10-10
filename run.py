from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from mafia.engine.errors import AbortGame
from mafia.engine.game import Game
from mafia.eventlog import JsonlWriter
from mafia.setup import DEFAULT_MODEL, NAMES, SetupError, build_agents, load_env


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--mafia", type=int, default=None, help="override mafia count")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--rpm", type=float, default=10, help="requests per minute cap")
    ap.add_argument("--random", action="store_true", help="use free random agents, no LLM")
    ap.add_argument("--log-dir", default="logs")
    args = ap.parse_args()

    try:
        agents, client = build_agents(
            NAMES[: args.players],
            use_random=args.random,
            model=args.model,
            rpm=args.rpm,
            seed=args.seed,
            log_dir=args.log_dir,
        )
    except SetupError as e:
        sys.exit(str(e))

    log = JsonlWriter(Path(args.log_dir) / f"game_{int(time.time())}.jsonl")

    def on_event(ev):
        log.write(ev)
        tag = "" if ev.visible_to is None or ev.kind == "setup" else "  (private)"
        print(f"{ev.text}{tag}", flush=True)

    errors = []

    def on_error(name, request, exc):
        errors.append(exc)
        print(f"!! {name} {request.kind} failed: {type(exc).__name__}: {exc}", flush=True)
        if len(errors) >= 6:
            raise AbortGame("Too many LLM errors, aborting. Check key, model name, and quota.")

    game = Game(
        agents,
        seed=args.seed,
        mafia_count=args.mafia,
        meta={"model": "random" if args.random else args.model},
        on_event=on_event,
        on_error=on_error,
    )
    try:
        game.run()
    except AbortGame as e:
        log.close()
        sys.exit(str(e))
    log.close()
    print(f"\nInvalid actions: {game.invalid_actions}. Log: {log.path}")
    if client:
        print(f"Calls: {client.calls}, cache hits: {client.cache_hits}, tokens in/out: {client.prompt_tokens}/{client.completion_tokens}")


if __name__ == "__main__":
    main()
