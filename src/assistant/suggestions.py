from assistant.models import Suggestion


def build_suggestions(capability_name: str, message: str) -> list[Suggestion]:
    if capability_name == "open_url":
        return [Suggestion(text="Ask me to open documentation next")]
    if capability_name == "search_files":
        return [Suggestion(text="Ask me to open one of the matching files next")]
    return [Suggestion(text="Ask me for the next step")]
