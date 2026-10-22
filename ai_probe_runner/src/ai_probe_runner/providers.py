from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResult:
    text: str
    response_id: str | None
    resolved_model: str | None
    citations: list[dict[str, Any]]
    usage: dict[str, Any] | None
    raw: dict[str, Any]
    search_count: int = 0


class Provider(Protocol):
    def ask(
        self,
        *,
        prompt: str,
        model: str,
        browsing: bool,
        max_output_tokens: int,
        effort: str | None = None,
        max_search_uses: int | None = None,
    ) -> ProviderResult: ...


class MockProvider:
    def ask(
        self,
        *,
        prompt: str,
        model: str,
        browsing: bool,
        max_output_tokens: int,
        effort: str | None = None,
        max_search_uses: int | None = None,
    ) -> ProviderResult:
        text = "Mock response: consult the relevant local emergency authority."
        raw = {
            "model": model,
            "browsing": browsing,
            "max_output_tokens": max_output_tokens,
            "effort": effort,
            "max_search_uses": max_search_uses,
            "input": prompt,
            "output": text,
        }
        return ProviderResult(
            text=text,
            response_id="mock-response",
            resolved_model=model,
            citations=[],
            usage=None,
            raw=raw,
            search_count=0,
        )


class OpenAIProvider:
    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install provider dependencies first") from exc
        self.client = OpenAI()

    def ask(
        self,
        *,
        prompt: str,
        model: str,
        browsing: bool,
        max_output_tokens: int,
        effort: str | None = None,
        max_search_uses: int | None = None,
    ) -> ProviderResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
        }
        if browsing:
            kwargs["tools"] = [{"type": "web_search"}]
            if max_search_uses is not None:
                kwargs["max_tool_calls"] = max_search_uses
        response = self.client.responses.create(**kwargs)
        raw = response.model_dump(mode="json")
        citations = [
            annotation
            for item in raw.get("output", [])
            for content in item.get("content", [])
            for annotation in content.get("annotations", [])
            if annotation.get("type") == "url_citation"
        ]
        return ProviderResult(
            text=response.output_text,
            response_id=raw.get("id"),
            resolved_model=raw.get("model"),
            citations=citations,
            usage=raw.get("usage"),
            raw=raw,
            search_count=sum(
                1
                for item in raw.get("output", [])
                if item.get("type") == "web_search_call"
            ),
        )


class AnthropicProvider:
    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Install provider dependencies first") from exc
        self.client = anthropic.Anthropic()

    def ask(
        self,
        *,
        prompt: str,
        model: str,
        browsing: bool,
        max_output_tokens: int,
        effort: str | None = None,
        max_search_uses: int | None = None,
    ) -> ProviderResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if browsing:
            kwargs["tools"] = [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_search_uses or 1,
                }
            ]
        if effort:
            kwargs["output_config"] = {"effort": effort}
        response = self.client.messages.create(**kwargs)
        raw = response.model_dump(mode="json")
        text = "".join(
            block.get("text", "")
            for block in raw.get("content", [])
            if block.get("type") == "text"
        )
        citations = [
            citation
            for block in raw.get("content", [])
            for citation in block.get("citations") or []
        ]
        return ProviderResult(
            text=text,
            response_id=raw.get("id"),
            resolved_model=raw.get("model"),
            citations=citations,
            usage=raw.get("usage"),
            raw=raw,
            search_count=sum(
                1
                for block in raw.get("content", [])
                if block.get("type") == "server_tool_use"
                and block.get("name") == "web_search"
            ),
        )


class GoogleProvider:
    def __init__(self) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Install provider dependencies first") from exc
        self.client = genai.Client()

    def ask(
        self,
        *,
        prompt: str,
        model: str,
        browsing: bool,
        max_output_tokens: int,
        effort: str | None = None,
        max_search_uses: int | None = None,
    ) -> ProviderResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "generation_config": {"max_output_tokens": max_output_tokens},
        }
        if browsing:
            kwargs["tools"] = [{"type": "google_search"}]
        response = self.client.interactions.create(**kwargs)
        raw = _model_to_dict(response)
        citations = [
            annotation
            for step in raw.get("steps", [])
            for block in step.get("content", []) or []
            for annotation in block.get("annotations", []) or []
            if annotation.get("type") == "url_citation"
        ]
        return ProviderResult(
            text=response.output_text,
            response_id=raw.get("id"),
            resolved_model=raw.get("model") or model,
            citations=citations,
            usage=raw.get("usage"),
            raw=raw,
            search_count=sum(
                1
                for step in raw.get("steps", [])
                if step.get("type") == "google_search_call"
            ),
        )


def _model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()
    raise TypeError(f"Cannot serialize provider response type: {type(value).__name__}")


def make_provider(name: str) -> Provider:
    providers = {
        "mock": MockProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
    }
    try:
        return providers[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {name}") from exc
