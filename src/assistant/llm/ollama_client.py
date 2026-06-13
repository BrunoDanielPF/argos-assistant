import httpx


class OllamaClient:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434/api",
        timeout_seconds: float = 30.0,
        keep_alive: str = "10m",
        think: bool = False,
        options: dict | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._keep_alive = keep_alive
        self._think = think
        self._options = options or {}

    def chat(self, messages: list[dict]) -> dict:
        return self._chat(messages, output_format="json")

    def chat_structured(
        self,
        messages: list[dict],
        schema: dict,
    ) -> dict:
        return self._chat(messages, output_format=schema)

    def _chat(
        self,
        messages: list[dict],
        *,
        output_format: str | dict,
    ) -> dict:
        response = httpx.post(
            f"{self._base_url}/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "format": output_format,
                "think": self._think,
                "keep_alive": self._keep_alive,
                "options": self._options,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["message"]["content"]
        return {"response": message}
