from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..setup import ROOT
from .runner import ConfigError, GameRunner, RunnerBusy
from ..setup import SetupError

WEB_ROOT = ROOT / "web"
GAME_ID_RE = re.compile(r"^game_\d+$")
MAX_BODY = 10_000
MAX_DRAIN = 1_000_000  # how much of an oversized body we read and discard before replying
UI_HEADER = "X-Mafia-UI"


def load_events(path: Path) -> list[dict]:
    """Read a JSONL log, skipping a partial last line from a game still being written."""
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return normalize_events(events)


def normalize_events(events: list[dict]) -> list[dict]:
    """Older logs have no setup event. Rebuild one so the viewer always finds roster and roles."""
    if not events or events[0].get("kind") == "setup":
        return events
    start = next((e for e in events if e.get("kind") == "start"), None)
    end = next((e for e in events if e.get("kind") == "end"), None)
    players: list[str] = []
    if start and "Players:" in start.get("text", ""):
        players = [p.strip() for p in start["text"].split("Players:")[1].strip(" .").split(",")]
    roles = (end or {}).get("data", {}).get("roles", {})
    setup = {
        "idx": -1,
        "day": 0,
        "phase": "night",
        "kind": "setup",
        "text": "Setup rebuilt from an older log",
        "data": {"players": players, "roles": roles, "personas": {}, "mafia_count": sum(1 for r in roles.values() if r == "mafia") if roles else None},
        "visible_to": [],
    }
    return [setup, *events]


def summarize(path: Path, runner: GameRunner) -> dict:
    events = load_events(path)
    setup = events[0]["data"] if events else {}
    end = next((e for e in reversed(events) if e.get("kind") == "end"), None)
    return {
        "id": path.stem,
        "modified": path.stat().st_mtime,
        "players": len(setup.get("players", [])),
        "mafia": setup.get("mafia_count"),
        "model": setup.get("model"),
        "winner": end["data"]["winner"] if end else None,
        "days": max((e.get("day", 0) for e in events), default=0),
        "running": runner.running and runner.game_id == path.stem,
    }


def make_handler(runner: GameRunner, log_dir: Path, port_ref: list[int]):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "MafiaUI"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        # ---- helpers ----------------------------------------------------
        def _allowed_hosts(self) -> set[str]:
            p = port_ref[0]
            return {f"127.0.0.1:{p}", f"localhost:{p}"}

        def _json(self, obj, status: int = 200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, message: str):
            self._json({"error": message}, status)

        def _host_ok(self) -> bool:
            # Rejects DNS rebinding: a foreign site pointed at 127.0.0.1 still sends its own Host.
            return self.headers.get("Host", "") in self._allowed_hosts()

        def _post_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{h}" for h in self._allowed_hosts()}:
                return False
            return self.headers.get(UI_HEADER) == "1"

        # ---- routing ----------------------------------------------------
        def do_GET(self):
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "bad host")
            path = self.path.split("?", 1)[0]
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/api/games":
                return self._list_games()
            if path == "/api/status":
                # has_key lets the page default to real players when an API key is configured.
                return self._json({**runner.status(), "has_key": bool(os.environ.get("GEMINI_API_KEY"))})
            if path == "/api/live":
                return self._live()
            m = re.match(r"^/api/games/([^/]+)$", path)
            if m:
                return self._one_game(m.group(1))
            if path.startswith("/api/"):
                return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return self._static(path)

        def _read_body(self) -> bytes | None:
            """Always consume the request body so a keep-alive connection stays in sync.

            Returns None (after replying and closing the connection) if the body is unusable.
            """
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self._error(HTTPStatus.BAD_REQUEST, "chunked bodies are not supported")
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                self.close_connection = True
                # Read (and discard) a bounded amount first. Closing with unread data makes the
                # OS reset the connection, and the client would see an error instead of our reply.
                remaining = min(max(length, 0), MAX_DRAIN)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_BODY else HTTPStatus.BAD_REQUEST, "bad body size")
                return None
            return self.rfile.read(length) if length else b""

        def do_POST(self):
            body = self._read_body()
            if body is None:
                return
            if not self._host_ok() or not self._post_ok():
                return self._error(HTTPStatus.FORBIDDEN, "request not allowed")
            path = self.path.split("?", 1)[0]
            if path == "/api/start":
                return self._start(body)
            if path == "/api/stop":
                return self._json({"stopping": runner.stop()})
            return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

        # ---- endpoints --------------------------------------------------
        def _static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB_ROOT / rel).resolve()
            if not target.is_relative_to(WEB_ROOT.resolve()) or not target.is_file():
                return self._error(HTTPStatus.NOT_FOUND, "not found")
            body = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _list_games(self):
            out = []
            for p in sorted(log_dir.glob("game_*.jsonl"), key=lambda q: q.stat().st_mtime, reverse=True):
                if GAME_ID_RE.match(p.stem):
                    try:
                        out.append(summarize(p, runner))
                    except (OSError, KeyError, ValueError):
                        continue
            self._json({"games": out})

        def _one_game(self, game_id: str):
            if not GAME_ID_RE.match(game_id):
                return self._error(HTTPStatus.BAD_REQUEST, "bad game id")
            p = log_dir / f"{game_id}.jsonl"
            if not p.is_file():
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            self._json({"id": game_id, "events": load_events(p)})

        def _start(self, body: bytes):
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send JSON")
            try:
                raw = json.loads(body)
                if not isinstance(raw, dict):
                    raise ValueError
            except ValueError:
                return self._error(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
            try:
                game_id = runner.start(raw)
            except RunnerBusy:
                return self._error(HTTPStatus.CONFLICT, "a game is already running")
            except (ConfigError, SetupError) as e:
                return self._error(HTTPStatus.BAD_REQUEST, str(e))
            self._json({"game_id": game_id})

        def _live(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                for kind, payload in runner.messages():
                    if kind == "keepalive":
                        chunk = b": keepalive\n\n"
                    elif kind == "message":
                        chunk = b"data: " + json.dumps(payload).encode() + b"\n\n"
                    else:
                        chunk = b"event: done\ndata: " + json.dumps(payload).encode() + b"\n\n"
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    return Handler


class QuietServer(ThreadingHTTPServer):
    """A browser that closes a tab resets its connection. That is normal, so do not print a traceback."""

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def create_server(runner: GameRunner, log_dir: str | Path = "logs", port: int = 8765) -> ThreadingHTTPServer:
    port_ref = [port]
    server = QuietServer(("127.0.0.1", port), make_handler(runner, Path(log_dir), port_ref))
    server.daemon_threads = True
    port_ref[0] = server.server_address[1]  # real port when 0 was requested
    return server
