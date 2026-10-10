import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mafia.llm import client as client_mod
from mafia.llm.client import ChatClient, retry_delay

OK = {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
DAILY = {"error": {"code": 429, "message": "quota", "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
PER_MINUTE = {"error": {"code": 429, "message": "slow down", "details": [{"retryDelay": "7s"}]}}


@pytest.fixture
def fake_api():
    """A local server that replays a scripted list of (status, body) responses."""
    state = {"script": [], "hits": 0}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            status, body = state["script"][min(state["hits"], len(state["script"]) - 1)]
            state["hits"] += 1
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    class Quiet(ThreadingHTTPServer):
        def handle_error(self, request, client_address):  # a client dropping its connection is not a failure
            pass

    server = Quiet(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def make(base, **kw):
    return ChatClient("m", api_key="k", base_url=base, rpm=0, cache_dir=None, **kw)


def test_retry_delay_parsing():
    assert retry_delay('..."retryDelay": "15s"...') == 16.0
    assert retry_delay("Please retry in 15.49s.") == pytest.approx(16.49)
    assert retry_delay("nothing here") == 0.0
    assert retry_delay('"retryDelay": "500s"') == 90.0  # capped


def test_daily_quota_fails_fast_without_retrying(fake_api, monkeypatch):
    state, base = fake_api
    state["script"] = [(429, DAILY)]
    sleeps = []
    monkeypatch.setattr(client_mod.time, "sleep", sleeps.append)
    with pytest.raises(RuntimeError, match="daily free tier quota"):
        make(base).chat([{"role": "user", "content": "hi"}])
    assert state["hits"] == 1 and sleeps == []


def test_per_minute_limit_waits_for_the_server_delay_then_succeeds(fake_api, monkeypatch):
    state, base = fake_api
    state["script"] = [(429, PER_MINUTE), (200, OK)]
    sleeps = []
    monkeypatch.setattr(client_mod.time, "sleep", sleeps.append)
    c = make(base)
    assert c.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert state["hits"] == 2 and 8.0 in sleeps  # 7s from the server plus a second of margin
    assert c.calls == 1 and c.prompt_tokens == 3


def test_server_errors_are_retried_and_then_reported(fake_api, monkeypatch):
    state, base = fake_api
    state["script"] = [(503, {"error": "busy"})]
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        make(base, max_retries=2).chat([{"role": "user", "content": "hi"}])
    assert state["hits"] == 3
