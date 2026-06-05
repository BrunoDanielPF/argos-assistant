import httpx


class OllamaClient:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434/api",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def chat(self, messages: list[dict]) -> dict:
        response = httpx.post(
            f"{self._base_url}/chat",
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["message"]["content"]
        return {"response": message}
