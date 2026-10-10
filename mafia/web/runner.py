from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

from ..engine import rules
from ..engine.errors import AbortGame, GameStopped
from ..engine.game import Game
from ..eventlog import JsonlWriter, event_to_dict
from ..setup import DEFAULT_MODEL, NAMES, build_agents

MAX_LLM_ERRORS = 6
MODEL_RE = re.compile(r"^[\w.:/-]{1,100}$")


class RunnerBusy(Exception):
    """A game is already running."""


class ConfigError(ValueError):
    """The start request had an invalid setting."""


def _int(raw: dict, key: str, default, lo: int, hi: int):
    val = raw.get(key)
    if val is None or val == "":
        return default
    try:
        val = int(val)
    except (TypeError, ValueError):
        raise ConfigError(f"{key} must be a whole number")
    if not lo <= val <= hi:
        raise ConfigError(f"{key} must be between {lo} and {hi}")
    return val


def parse_config(raw: dict) -> dict:
    players = _int(raw, "players", 6, 6, 10)
    mafia = _int(raw, "mafia", None, 1, 10)
    try:
        rules.role_counts(players, mafia)
    except ValueError as e:
        raise ConfigError(str(e))
    seed = _int(raw, "seed", None, 0, 2**31 - 1)
    model = str(raw.get("model") or DEFAULT_MODEL).strip()
    if not MODEL_RE.match(model):
        raise ConfigError("model name has invalid characters")
    try:
        rpm = float(raw.get("rpm") or 10)
    except (TypeError, ValueError):
        raise ConfigError("rpm must be a number")
    if not 1 <= rpm <= 600:
        raise ConfigError("rpm must be between 1 and 600")
    try:
        delay = float(raw.get("delay") or 0)
    except (TypeError, ValueError):
        raise ConfigError("delay must be a number")
    if not 0 <= delay <= 5:
        raise ConfigError("delay must be between 0 and 5 seconds")
    return {
        "players": players,
        "mafia": mafia,
        "seed": seed,
        "model": model,
        "rpm": rpm,
        "random": bool(raw.get("random")),
        "delay": delay,
    }


class GameRunner:
    """Runs one game at a time on a background thread and lets many viewers follow it.

    Events are kept in memory (and written to JSONL). Viewers read them by position, so a
    late joiner replays history and then receives new events as they arrive.
    """

    def __init__(self, log_dir: str | Path = "logs", agent_factory: Callable | None = None):
        self.log_dir = Path(log_dir)
        self.agent_factory = agent_factory or build_agents
        self.cond = threading.Condition()
        self.events: list[dict] = []
        self.gen = 0
        self.running = False
        self.done = True
        self.final: dict = {"status": "idle"}
        self.game_id: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- control --------------------------------------------------------
    def start(self, raw: dict) -> str:
        cfg = parse_config(raw)
        with self.cond:
            if self.running:
                raise RunnerBusy()
            self.running = True
        try:
            names = NAMES[: cfg["players"]]
            agents, client = self.agent_factory(
                names,
                use_random=cfg["random"],
                model=cfg["model"],
                rpm=cfg["rpm"],
                seed=cfg["seed"],
                log_dir=self.log_dir,
                delay=cfg["delay"],
            )
            game_id = self._new_id()
            log = JsonlWriter(self.log_dir / f"{game_id}.jsonl")
        except BaseException:
            with self.cond:
                self.running = False
            raise

        errors: list[Exception] = []

        def on_event(ev):
            log.write(ev)
            with self.cond:
                self.events.append(event_to_dict(ev))
                self.cond.notify_all()

        def on_error(name, request, exc):
            errors.append(exc)
            print(f"[game] {name} {request.kind} failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if len(errors) >= MAX_LLM_ERRORS:
                raise AbortGame("Too many LLM errors. Check the API key, model name, and quota.")

        self._stop.clear()
        game = Game(
            agents,
            seed=cfg["seed"],
            mafia_count=cfg["mafia"],
            meta={"model": "random" if cfg["random"] else cfg["model"]},
            on_event=on_event,
            on_error=on_error,
            should_stop=self._stop.is_set,
        )
        with self.cond:
            self.gen += 1
            self.events = []
            self.done = False
            self.final = {}
            self.game_id = game_id
        self._thread = threading.Thread(
            target=self._run, args=(game, log, client, game_id), daemon=True, name=game_id
        )
        self._thread.start()
        return game_id

    def _new_id(self) -> str:
        n = int(time.time())
        while (self.log_dir / f"game_{n}.jsonl").exists():
            n += 1
        return f"game_{n}"

    def _run(self, game: Game, log: JsonlWriter, client, game_id: str) -> None:
        status, message = "finished", ""
        try:
            game.run()
        except GameStopped:
            status = "stopped"
        except AbortGame as e:
            status, message = "error", str(e)
        except Exception as e:  # keep the server alive whatever the game does
            status, message = "error", f"{type(e).__name__}: {e}"
        finally:
            log.close()
            final = {"status": status, "message": message, "game_id": game_id, "invalid_actions": game.invalid_actions}
            if client:
                final.update(calls=client.calls, prompt_tokens=client.prompt_tokens, completion_tokens=client.completion_tokens)
            with self.cond:
                self.final = final
                self.done = True
                self.running = False
                self.cond.notify_all()

    def stop(self) -> bool:
        with self.cond:
            running = self.running
        if running:
            self._stop.set()
        return running

    def wait_idle(self, timeout: float = 10) -> bool:
        with self.cond:
            return self.cond.wait_for(lambda: not self.running, timeout=timeout)

    # ---- viewing --------------------------------------------------------
    def status(self) -> dict:
        with self.cond:
            return {
                "running": self.running,
                "game_id": self.game_id,
                "events": len(self.events),
                "final": dict(self.final),
            }

    def messages(self) -> Iterator[tuple[str, dict | None]]:
        """Yield ('message', event) for each event, ('keepalive', None) while idle, then ('done', final)."""
        with self.cond:
            gen = self.gen
        i = 0
        while True:
            with self.cond:
                self.cond.wait_for(lambda: self.gen != gen or i < len(self.events) or self.done, timeout=15)
                if self.gen != gen:
                    return
                batch = self.events[i:]
                i += len(batch)
                finished = self.done and i >= len(self.events)
                final = dict(self.final)
            for e in batch:
                yield "message", e
            if finished:
                yield "done", final
                return
            if not batch:
                yield "keepalive", None
