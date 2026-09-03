"""Provider construction. Fake never needs keys."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_eval.providers import (
    AnthropicProvider,
    FakeProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderError,
    get_provider,
    parse_model_spec,
    resolve_ollama_base_url,
)


def test_fake_ignores_missing_keys() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("OLLAMA_API_KEY", None)
    provider = get_provider("fake")
    assert isinstance(provider, FakeProvider)
    msg = provider.complete(
        [{"role": "user", "content": "Return JSON for CVE-2026-44012 please"}],
        task_id="cc-cve-extract",
    )
    assert "CVE-2026-44012" in msg.content


def test_openai_complete_requires_key() -> None:
    provider = OpenAICompatibleProvider(model="gpt-4o-mini", api_key="")
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        provider.complete([{"role": "user", "content": "hi"}])


def test_anthropic_complete_requires_key() -> None:
    provider = AnthropicProvider(model="claude-3-5-haiku-latest", api_key="")
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        provider.complete([{"role": "user", "content": "hi"}])


def test_ollama_cloud_requires_key() -> None:
    provider = OllamaProvider(model="llama3.2", api_key="", base_url="https://ollama.com/v1")
    with pytest.raises(ProviderError, match="OLLAMA_API_KEY"):
        provider.complete([{"role": "user", "content": "hi"}])


def test_ollama_parses_colon_model_ids() -> None:
    kind, model = parse_model_spec("ollama:gpt-oss:20b")
    assert kind == "ollama"
    assert model == "gpt-oss:20b"
    provider = get_provider("ollama:kimi-k2.5:cloud")
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "kimi-k2.5:cloud"


def test_ollama_defaults_to_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    provider = get_provider("ollama:llama3.2")
    assert provider.base_url == "https://ollama.com/v1"
    assert provider.api_key == "test-key"


def test_ollama_host_does_not_override_cloud_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    assert resolve_ollama_base_url() == "https://ollama.com/v1"


def test_ollama_local_url_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    provider = get_provider("ollama:llama3.2")
    assert provider.base_url == "http://127.0.0.1:11434/v1"
    assert provider.api_key == "ollama"


def test_ollama_complete_sends_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "gpt-oss:20b",
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                "choices": [{"message": {"content": "Atlanta is 72 F and sunny."}}],
            },
        )

    monkeypatch.setattr("agent_eval.providers.httpx.post", fake_post)
    provider = OllamaProvider(
        model="gpt-oss:20b",
        api_key="secret-ollama",
        base_url="https://ollama.com/v1",
    )
    msg = provider.complete([{"role": "user", "content": "hi"}])
    assert msg.content == "Atlanta is 72 F and sunny."
    assert msg.prompt_tokens == 11
    assert msg.completion_tokens == 7
    assert msg.api_model == "gpt-oss:20b"
    assert captured["url"] == "https://ollama.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret-ollama"
    assert captured["json"]["model"] == "gpt-oss:20b"
    assert captured["json"]["temperature"] == 0


def test_bad_model_spec() -> None:
    with pytest.raises(ProviderError):
        get_provider("together:qwen")


def test_dotenv_fills_missing_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_eval.cli import load_project_env

    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OLLAMA_API_KEY=from-file\n", encoding="utf-8")
    assert load_project_env(env) == env
    assert os.environ["OLLAMA_API_KEY"] == "from-file"


def test_dotenv_does_not_override_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_eval.cli import load_project_env

    monkeypatch.setenv("OLLAMA_API_KEY", "from-shell")
    env = tmp_path / ".env"
    env.write_text("OLLAMA_API_KEY=from-file\n", encoding="utf-8")
    load_project_env(env)
    assert os.environ["OLLAMA_API_KEY"] == "from-shell"


def test_dotenv_missing_file_is_noop(tmp_path: Path) -> None:
    from agent_eval.cli import load_project_env

    assert load_project_env(tmp_path / ".env") is None
