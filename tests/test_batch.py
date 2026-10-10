import json

from mafia.batch import run_batch


def quiet(_msg):
    pass


def test_batch_of_random_games_writes_logs_and_summary(tmp_path):
    data = run_batch(4, use_random=True, log_dir=tmp_path, seed_start=10, progress=quiet)
    assert [r["seed"] for r in data["results"]] == [10, 11, 12, 13]
    assert all(r["status"] == "finished" and r["winner"] in ("town", "mafia") for r in data["results"])
    assert len(list(tmp_path.glob("game_*.jsonl"))) == 4
    saved = json.loads((tmp_path / next(p.name for p in tmp_path.glob("batch_*.json"))).read_text())
    assert len(saved["results"]) == 4 and saved["config"]["model"] == "random"


def test_batch_resumes_and_skips_finished_seeds(tmp_path):
    summary = tmp_path / "s.json"
    run_batch(2, use_random=True, log_dir=tmp_path, summary_path=summary, progress=quiet)
    before = len(list(tmp_path.glob("game_*.jsonl")))
    lines = []
    data = run_batch(3, use_random=True, log_dir=tmp_path, summary_path=summary, progress=lines.append)
    assert len(list(tmp_path.glob("game_*.jsonl"))) == before + 1  # only the new seed was played
    assert sum("already finished" in l for l in lines) == 2
    assert len(data["results"]) == 3


def test_cache_flag_reaches_the_agent_builder(tmp_path):
    seen = []

    def spy(names, **kw):
        seen.append(kw["cache"])
        from mafia.setup import build_agents
        return build_agents(names, use_random=True, **{k: v for k, v in kw.items() if k in ("seed", "log_dir")})

    run_batch(1, use_random=True, log_dir=tmp_path, builder=spy, progress=quiet)
    run_batch(1, use_random=True, log_dir=tmp_path, builder=spy, progress=quiet, cache=False, seed_start=5)
    assert seen == [True, False]


def test_build_agents_turns_the_cache_off(tmp_path, monkeypatch):
    from mafia.setup import build_agents

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    _, on = build_agents(["Ann"] * 1, log_dir=tmp_path)
    _, off = build_agents(["Ann"] * 1, log_dir=tmp_path, cache=False)
    assert on.cache_dir is not None and off.cache_dir is None


class Broken:
    def act(self, view, request):
        raise RuntimeError("quota exhausted")


def test_batch_stops_after_consecutive_failures(tmp_path):
    builder = lambda names, **kw: ({n: Broken() for n in names}, None)
    lines = []
    data = run_batch(6, use_random=True, log_dir=tmp_path, builder=builder, progress=lines.append)
    assert len(data["results"]) == 2  # gave up after two failed games, not six
    assert all(r["status"] == "error" for r in data["results"])
    assert any("Stopping" in l for l in lines)
