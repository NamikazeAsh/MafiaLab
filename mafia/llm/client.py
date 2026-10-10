from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
DAILY_QUOTA_MARKER = "PerDay"  # appears in the quota id of Gemini's daily limit errors


def retry_delay(detail: str, cap: float = 90.0) -> float:
    """Seconds the server asked us to wait ('retryDelay': '15s' or 'Please retry in 15.4s'), else 0."""
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', detail) or re.search(r"retry in (\d+(?:\.\d+)?)s", detail)
    return min(float(m.group(1)) + 1, cap) if m else 0.0


class LLMClient(Protocol):
    def chat(self, messages: list[dict], max_tokens: int = 300, temperature: float = 0.8) -> str: ...


class ChatClient:
    """OpenAI compatible chat client (Gemini, Groq, Ollama, OpenRouter) using only the stdlib.

    Adds a minimum interval between calls (free tier RPM), backoff on 429/5xx,
    and an on disk cache so a crashed game can resume without repeating calls.
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = GEMINI_BASE,
        rpm: float = 10,
        cache_dir: str | Path | None = ".cache/llm",
        trace_path: str | Path | None = None,
        max_retries: int = 6,
        timeout: float = 60,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.min_interval = 60.0 / rpm if rpm else 0.0
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_retries = max_retries
        self.timeout = timeout
        self.trace_path = Path(trace_path) if trace_path else None
        self._last_call = 0.0
        self._lock = threading.Lock()
        self.calls = 0
        self.cache_hits = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, messages, max_tokens, temperature) -> str:
        blob = json.dumps([self.model, messages, max_tokens, temperature], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _throttle(self):
        with self._lock:
            wait = self._last_call + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _trace(self, messages, text):
        if self.trace_path:
            with self.trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"messages": messages, "response": text}) + "\n")

    def chat(self, messages: list[dict], max_tokens: int = 300, temperature: float = 0.8) -> str:
        text = self._chat(messages, max_tokens, temperature)
        self._trace(messages, text)
        return text

    def _chat(self, messages: list[dict], max_tokens: int, temperature: float) -> str:
        key = self._key(messages, max_tokens, temperature)
        path = self.cache_dir / f"{key}.txt" if self.cache_dir else None
        if path and path.exists():
            self.cache_hits += 1
            return path.read_text(encoding="utf-8")

        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        delay = 4.0
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.load(resp)
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                if e.code == 429 and DAILY_QUOTA_MARKER in detail:
                    # A daily cap will not clear by waiting a few seconds, so fail at once.
                    raise RuntimeError(
                        "LLM HTTP 429: the daily free tier quota for this model is used up. "
                        "It resets daily. Wait, or try another model."
                    ) from e
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(retry_delay(detail) or delay)
                    delay = min(delay * 2, 60)
                    continue
                raise RuntimeError(f"LLM HTTP {e.code}: {detail[:600]}") from e
            except (urllib.error.URLError, TimeoutError):
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
                raise

        self.calls += 1
        usage = data.get("usage") or {}
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        text = (data["choices"][0]["message"].get("content") or "").strip()
        if path and text:
            path.write_text(text, encoding="utf-8")
        return text
