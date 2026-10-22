from ai_probe_runner.providers import (
    AnthropicProvider,
    GoogleProvider,
    OpenAIProvider,
)


class FakeResponse:
    output_text = "Test response"

    def __init__(self, raw):
        self.raw = raw

    def model_dump(self, mode="json"):
        return self.raw


class Recorder:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_openai_receives_frozen_output_limit():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "openai-1",
                "model": "gpt-test",
                "output": [],
                "usage": {},
            }
        )
    )
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = type("Client", (), {"responses": recorder})()

    provider.ask(
        prompt="test",
        model="gpt-test",
        browsing=False,
        max_output_tokens=2048,
    )

    assert recorder.kwargs["max_output_tokens"] == 2048


def test_openai_search_is_capped_and_counted():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "openai-1",
                "model": "gpt-test",
                "output": [{"type": "web_search_call"}],
                "usage": {},
            }
        )
    )
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = type("Client", (), {"responses": recorder})()

    result = provider.ask(
        prompt="test",
        model="gpt-test",
        browsing=True,
        max_output_tokens=640,
        max_search_uses=1,
    )

    assert recorder.kwargs["max_tool_calls"] == 1
    assert result.search_count == 1


def test_anthropic_receives_frozen_output_limit():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "anthropic-1",
                "model": "claude-test",
                "content": [{"type": "text", "text": "Test response"}],
                "usage": {},
            }
        )
    )
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = type("Client", (), {"messages": recorder})()

    provider.ask(
        prompt="test",
        model="claude-test",
        browsing=False,
        max_output_tokens=2048,
    )

    assert recorder.kwargs["max_tokens"] == 2048


def test_anthropic_receives_explicit_low_effort():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "anthropic-1",
                "model": "claude-haiku-test",
                "content": [{"type": "text", "text": "Test response"}],
                "usage": {},
            }
        )
    )
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = type("Client", (), {"messages": recorder})()

    provider.ask(
        prompt="test",
        model="claude-haiku-test",
        browsing=False,
        max_output_tokens=1024,
        effort="low",
    )

    assert recorder.kwargs["max_tokens"] == 1024
    assert recorder.kwargs["output_config"] == {"effort": "low"}


def test_anthropic_search_is_capped_and_counted():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "anthropic-1",
                "model": "claude-test",
                "content": [
                    {"type": "server_tool_use", "name": "web_search"},
                    {"type": "text", "text": "Test response"},
                ],
                "usage": {},
            }
        )
    )
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = type("Client", (), {"messages": recorder})()

    result = provider.ask(
        prompt="test",
        model="claude-test",
        browsing=True,
        max_output_tokens=640,
        max_search_uses=1,
    )

    assert recorder.kwargs["tools"][0]["max_uses"] == 1
    assert result.search_count == 1


def test_google_receives_frozen_output_limit():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "google-1",
                "model": "gemini-test",
                "steps": [],
                "usage": {},
            }
        )
    )
    provider = GoogleProvider.__new__(GoogleProvider)
    provider.client = type("Client", (), {"interactions": recorder})()

    provider.ask(
        prompt="test",
        model="gemini-test",
        browsing=False,
        max_output_tokens=2048,
    )

    assert recorder.kwargs["generation_config"] == {"max_output_tokens": 2048}


def test_google_search_calls_are_counted():
    recorder = Recorder(
        FakeResponse(
            {
                "id": "google-1",
                "model": "gemini-test",
                "steps": [{"type": "google_search_call"}],
                "usage": {},
            }
        )
    )
    provider = GoogleProvider.__new__(GoogleProvider)
    provider.client = type("Client", (), {"interactions": recorder})()

    result = provider.ask(
        prompt="test",
        model="gemini-test",
        browsing=True,
        max_output_tokens=640,
    )

    assert recorder.kwargs["tools"] == [{"type": "google_search"}]
    assert result.search_count == 1
