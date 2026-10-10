from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from .engine.errors import AbortGame
from .engine.game import Game
from .eventlog import JsonlWriter
from .setup import DEFAULT_MODEL, NAMES, build_agents

MAX_LLM_ERRORS = 6
STOP_AFTER_FAILURES = 2  # consecutive failed games before the batch gives up (quota or outage)


def _unique_id(log_dir: Path) -> str:
    n = int(time.time())
    while (log_dir / f"game_{n}.jsonl").exists():
        n += 1
    return f"game_{n}"


def play_one(
    seed: int,
    *,
    players: int,
    mafia: int | None,
    model: str,
    rpm: float,
    use_random: bool,
    log_dir: Path,
    builder: Callable = build_agents,
    cache: bool = True,
) -> dict:
    """Play one game to the end (or failure) and return a result row."""
    t0 = time.time()
    agents, client = builder(
        NAMES[:players], use_random=use_random, model=model, rpm=rpm, seed=seed, log_dir=log_dir, cache=cache
    )
    game_id = _unique_id(log_dir)
    log = JsonlWriter(log_dir / f"{game_id}.jsonl")
    errors: list[str] = []

    def on_error(name, request, exc):
        errors.append(f"{type(exc).__name__}: {exc}")
        if len(errors) >= MAX_LLM_ERRORS:
            raise AbortGame("too many LLM errors")

    game = Game(
        agents,
        seed=seed,
        mafia_count=mafia,
        meta={"model": "random" if use_random else model},
        on_event=log.write,
        on_error=on_error,
    )
    status, winner, error = "finished", None, ""
    try:
        winner = game.run()
    except AbortGame as e:
        status, error = "error", str(e)
    except Exception as e:  # a crash in one game must not lose the rest of the batch
        status, error = "error", f"{type(e).__name__}: {e}"
    finally:
        log.close()
    st = game.state
    return {
        "seed": seed,
        "game_id": game_id,
        "status": status,
        "winner": winner,
        "days": st.day,
        "players": players,
        "mafia": len(st.mafia_names()),
        "roles": {n: p.role.value for n, p in st.players.items()},
        "invalid_actions": game.invalid_actions,
        "llm_errors": len(errors),
        "last_error": errors[-1] if errors else "",
        "calls": client.calls if client else 0,
        "cache_hits": client.cache_hits if client else 0,
        "prompt_tokens": client.prompt_tokens if client else 0,
        "completion_tokens": client.completion_tokens if client else 0,
        "seconds": round(time.time() - t0, 1),
        "error": error,
    }


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def run_batch(
    games: int,
    *,
    players: int = 6,
    seed_start: int = 100,
    mafia: int | None = None,
    model: str = DEFAULT_MODEL,
    rpm: float = 10,
    log_dir: str | Path = "logs",
    use_random: bool = False,
    summary_path: str | Path | None = None,
    builder: Callable = build_agents,
    progress: Callable[[str], None] = print,
    cache: bool = True,
) -> dict:
    """Run games with consecutive seeds. Saves a summary after every game and resumes from it."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = Path(summary_path) if summary_path else log_dir / f"batch_{int(time.time())}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {
            "config": {
                "games": games, "players": players, "mafia": mafia, "seed_start": seed_start,
                "model": "random" if use_random else model, "rpm": rpm,
            },
            "results": [],
        }
    done = {r["seed"] for r in data["results"] if r["status"] == "finished"}
    failures = 0
    for i in range(games):
        seed = seed_start + i
        if seed in done:
            progress(f"[{i + 1}/{games}] seed {seed} already finished, skipping")
            continue
        res = play_one(
            seed, players=players, mafia=mafia, model=model, rpm=rpm,
            use_random=use_random, log_dir=log_dir, builder=builder, cache=cache,
        )
        data["results"] = [r for r in data["results"] if r["seed"] != seed] + [res]
        _save(path, data)
        if res["status"] == "finished":
            failures = 0
            tokens = res["prompt_tokens"] + res["completion_tokens"]
            progress(
                f"[{i + 1}/{games}] seed {seed}: {res['winner']} won in {res['days']} days, "
                f"{res['calls']} calls, {tokens:,} tokens, {res['invalid_actions']} invalid, "
                f"{res['seconds'] / 60:.1f} min"
            )
        else:
            failures += 1
            progress(f"[{i + 1}/{games}] seed {seed}: FAILED ({res['error']}) {res['last_error']}")
            if failures >= STOP_AFTER_FAILURES:
                progress(f"Stopping: {failures} failed games in a row. Rerun the same command to resume.")
                break
    data["summary_path"] = str(path)
    return data
