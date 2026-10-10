import http.client
import json
import threading
import time

import pytest

from mafia.web.runner import GameRunner
from mafia.web.server import create_server, load_events


class Slow:
    """Plays legal moves but slowly, so a test can act while the game is running."""

    def act(self, view, request):
        time.sleep(0.02)
        if request.kind in ("speak", "mafia_speak"):
            return "hi"
        return request.options[0]


class Broken:
    def act(self, view, request):
        raise RuntimeError("api down")


def factory_of(cls):
    return lambda names, **kw: ({n: cls() for n in names}, None)


@pytest.fixture
def app(tmp_path):
    started = []

    def make(agent_factory=None):
        runner = GameRunner(tmp_path, agent_factory=agent_factory) if agent_factory else GameRunner(tmp_path)
        server = create_server(runner, tmp_path, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        started.append((runner, server))
        return runner, server.server_address[1]

    yield make
    for runner, server in started:
        runner.stop()
        runner.wait_idle(5)
        server.shutdown()
        server.server_close()


def call(port, method, path, body=None, headers=None, ui=True):
    hdrs = dict(headers or {})
    if method == "POST":
        hdrs.setdefault("Content-Type", "application/json")
        if ui:
            hdrs.setdefault("X-Mafia-UI", "1")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(data)
    except ValueError:
        return resp.status, data


def start_random(port, **extra):
    return call(port, "POST", "/api/start", {"players": 6, "seed": 1, "random": True, **extra})


def test_serves_index_and_blocks_traversal(app):
    _, port = app()
    status, body = call(port, "GET", "/")
    assert status == 200 and b"<html" in body
    assert call(port, "GET", "/../mafia/setup.py")[0] == 404


def test_rejects_foreign_host(app):
    _, port = app()
    assert call(port, "GET", "/api/games", headers={"Host": "evil.example"})[0] == 403


def test_post_needs_ui_header_and_local_origin(app):
    _, port = app()
    assert start_random_no_header(port)[0] == 403
    status, _ = call(port, "POST", "/api/start", {"random": True}, headers={"Origin": "http://evil.example"})
    assert status == 403


def start_random_no_header(port):
    return call(port, "POST", "/api/start", {"random": True}, ui=False)


def test_bad_config_and_content_type(app):
    _, port = app()
    assert call(port, "POST", "/api/start", {"players": 99})[0] == 400
    assert call(port, "POST", "/api/start", {"players": 6, "mafia": 5})[0] == 400
    assert call(port, "POST", "/api/start", {"model": "bad model!;"})[0] == 400
    assert call(port, "POST", "/api/start", {"random": True, "delay": 99})[0] == 400
    assert call(port, "POST", "/api/start", {"random": True}, headers={"Content-Type": "text/plain"})[0] == 415


def test_missing_api_key_is_a_clean_400(app, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _, port = app()
    status, body = call(port, "POST", "/api/start", {"players": 6})
    assert status == 400 and "GEMINI_API_KEY" in body["error"]
    assert call(port, "GET", "/api/status")[1]["running"] is False


def test_status_reports_whether_a_key_is_configured(app, monkeypatch):
    _, port = app()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert call(port, "GET", "/api/status")[1]["has_key"] is False
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert call(port, "GET", "/api/status")[1]["has_key"] is True


def test_random_game_end_to_end(app):
    runner, port = app()
    status, body = start_random(port)
    assert status == 200
    game_id = body["game_id"]
    assert runner.wait_idle(10)

    status, games = call(port, "GET", "/api/games")
    row = next(g for g in games["games"] if g["id"] == game_id)
    assert row["winner"] in ("town", "mafia") and row["players"] == 6 and row["mafia"] == 1

    status, one = call(port, "GET", f"/api/games/{game_id}")
    assert one["events"][0]["kind"] == "setup" and one["events"][-1]["kind"] == "end"


def test_post_body_is_consumed_so_keepalive_stays_in_sync(app):
    """Regression: an unread POST body used to be parsed as the next request line."""
    _, port = app()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    hdrs = {"Content-Type": "application/json", "X-Mafia-UI": "1"}
    conn.request("POST", "/api/stop", body="{}", headers=hdrs)
    r1 = conn.getresponse()
    r1.read()
    assert r1.status == 200
    conn.request("GET", "/api/status")
    r2 = conn.getresponse()
    assert r2.status == 200 and json.loads(r2.read())["running"] is False
    # a rejected POST must also drain its body
    conn.request("POST", "/api/stop", body='{"x": 1}', headers={"Content-Type": "application/json"})
    r3 = conn.getresponse()
    r3.read()
    assert r3.status == 403
    conn.request("GET", "/api/status")
    assert conn.getresponse().status == 200
    conn.close()


def test_oversized_post_is_rejected(app):
    _, port = app()
    status, _ = call(port, "POST", "/api/start", {"junk": "x" * 20000})
    assert status == 413


def test_dropped_connections_do_not_print_tracebacks(app, capfd):
    import socket

    _, port = app()
    for _ in range(5):
        s = socket.create_connection(("127.0.0.1", port))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")  # close with RST
        s.close()
    assert call(port, "GET", "/api/status")[0] == 200  # the server is still fine
    assert "Traceback" not in capfd.readouterr().err


def test_favicon_is_quiet(app):
    _, port = app()
    assert call(port, "GET", "/favicon.ico")[0] == 204


def test_game_id_validation(app):
    _, port = app()
    assert call(port, "GET", "/api/games/..%2F..%2Fsecret")[0] == 400
    assert call(port, "GET", "/api/games/game_abc")[0] == 400
    assert call(port, "GET", "/api/games/game_1")[0] == 404


def test_sse_replays_history_then_done(app):
    runner, port = app()
    start_random(port)
    assert runner.wait_idle(10)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/api/live")
    resp = conn.getresponse()
    assert resp.getheader("Content-Type") == "text/event-stream"
    text = resp.read().decode()
    conn.close()
    blocks = [b for b in text.split("\n\n") if b.strip()]
    events = [json.loads(b[len("data: "):]) for b in blocks if b.startswith("data: ")]
    done = [json.loads(b.split("data: ", 1)[1]) for b in blocks if b.startswith("event: done")]
    assert events[0]["kind"] == "setup" and events[-1]["kind"] == "end"
    assert len(done) == 1 and done[0]["status"] == "finished"
    assert blocks[-1].startswith("event: done")


def test_second_start_is_409_and_stop_works(app):
    runner, port = app(factory_of(Slow))
    assert start_random(port)[0] == 200
    assert start_random(port)[0] == 409
    assert call(port, "POST", "/api/stop", {})[1]["stopping"] is True
    assert runner.wait_idle(10)
    assert runner.final["status"] == "stopped"
    # a fresh game can start after a stop
    assert start_random(port)[0] == 200


def test_repeated_llm_errors_abort_the_game(app):
    runner, port = app(factory_of(Broken))
    assert start_random(port)[0] == 200
    assert runner.wait_idle(10)
    assert runner.final["status"] == "error" and "LLM errors" in runner.final["message"]


def test_old_logs_get_a_rebuilt_setup_event(tmp_path):
    lines = [
        {"idx": 0, "day": 0, "phase": "night", "kind": "start", "text": "Game start. Players: Ann, Bob, Cy.", "data": {}, "visible_to": None},
        {"idx": 1, "day": 2, "phase": "day", "kind": "end", "text": "town wins.", "data": {"winner": "town", "roles": {"Ann": "mafia", "Bob": "doctor", "Cy": "villager"}}, "visible_to": None},
    ]
    p = tmp_path / "game_1.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n{partial", encoding="utf-8")
    events = load_events(p)
    assert events[0]["kind"] == "setup"
    assert events[0]["data"]["players"] == ["Ann", "Bob", "Cy"]
    assert events[0]["data"]["roles"]["Ann"] == "mafia"
    assert len(events) == 3  # the partial last line is skipped


def test_unfinished_old_log_has_unknown_mafia_count(tmp_path):
    p = tmp_path / "game_2.jsonl"
    line = {"idx": 0, "day": 0, "phase": "night", "kind": "start", "text": "Game start. Players: Ann, Bob.", "data": {}, "visible_to": None}
    p.write_text(json.dumps(line) + "\n", encoding="utf-8")
    assert load_events(p)[0]["data"]["mafia_count"] is None
