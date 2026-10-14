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
