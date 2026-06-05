from assistant.models import Suggestion
from assistant.suggestions import build_suggestions


def test_build_suggestions_for_open_url_action():
    suggestions = build_suggestions("open_url", "Opened https://ollama.com")

    assert suggestions == [Suggestion(text="Ask me to open documentation next")]
