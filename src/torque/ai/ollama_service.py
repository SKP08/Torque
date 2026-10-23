from loguru import logger

from torque.system.config_service import load_config


class OllamaUnavailableError(RuntimeError):
    """Ollama isn't running or the model isn't installed."""


class OllamaService:

    def __init__(self, model=None, chat=None):

        config = load_config()

        self.model = model or config["llm_model"]
        self.num_predict = config["llm_num_predict"]

        # Injectable for tests.
        self._chat = chat

        logger.success(f"Ollama model: {self.model}")

        self._check_model()

    def _check_model(self):
        """Warn early (not fatally) if the model isn't installed."""

        if self._chat is not None:
            return

        try:
            import ollama

            installed = {m.model for m in ollama.list().models}

            if not any(name == self.model or name.startswith(f"{self.model}:") for name in installed):
                logger.warning(
                    f"Ollama model '{self.model}' not found. Run: ollama pull {self.model}"
                )

        except Exception:  # noqa: BLE001
            logger.warning("Could not reach Ollama. Start it with: ollama serve")

    def chat(self, messages: list) -> str:

        chat = self._chat

        if chat is None:
            from ollama import chat

        try:
            response = chat(
                model=self.model,
                keep_alive="30m",
                options={
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": self.num_predict,
                    "num_ctx": 4096,
                },
                messages=messages,
            )

        except Exception as error:  # noqa: BLE001
            raise OllamaUnavailableError(str(error)) from error

        answer = response["message"]["content"].strip()

        logger.success(f"Torque: {answer}")

        return answer
