import threading

from loguru import logger

from torque.system.config_service import load_config


class OllamaUnavailableError(RuntimeError):
    """Ollama isn't running or the model isn't installed."""


class OllamaService:

    def __init__(self, model=None, chat=None):

        config = load_config()

        self.model = model or config["llm_model"]
        self.num_predict = config["llm_num_predict"]
        self.num_ctx = config["llm_num_ctx"]

        # True when the last reply was cut off by the token limit.
        self.truncated = False

        # Injectable for tests.
        self._chat = chat

        logger.success(f"Ollama model: {self.model}")

        if chat is None:
            self._check_model()

    # ----------------------------------------------------------

    def _check_model(self):
        """Warn early (not fatally) if the model isn't installed."""

        try:
            import ollama

            installed = {m.model for m in ollama.list().models}

            if not any(name == self.model or name.startswith(f"{self.model}:") for name in installed):
                logger.warning(
                    f"Ollama model '{self.model}' not found. Run: ollama pull {self.model}"
                )

        except Exception:  # noqa: BLE001
            logger.warning("Could not reach Ollama. Start it with: ollama serve")

    def warm_up(self):
        """
        Load the model into memory in the background so the first real
        question is not slowed down by a cold start.
        """

        def load():
            try:
                import ollama

                ollama.generate(
                    model=self.model,
                    prompt="",
                    keep_alive="1h",
                    options={"num_predict": 1},
                )

                logger.info("Language model loaded.")

            except Exception:  # noqa: BLE001
                logger.debug("LLM warm-up failed.", exc_info=True)

        threading.Thread(target=load, name="TorqueLLMWarmup", daemon=True).start()

    # ----------------------------------------------------------

    def _options(self):

        return {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": self.num_predict,
            "num_ctx": self.num_ctx,
        }

    def chat_stream(self, messages: list):
        """
        Yield the reply piece by piece as the model generates it. Raises
        OllamaUnavailableError if Ollama can't be reached.
        """

        chat = self._chat

        if chat is None:
            from ollama import chat

        self.truncated = False

        try:
            stream = chat(
                model=self.model,
                keep_alive="1h",
                options=self._options(),
                messages=messages,
                stream=True,
            )

            for chunk in stream:

                piece = chunk["message"]["content"]

                if piece:
                    yield piece

                if chunk.get("done"):
                    self.truncated = chunk.get("done_reason") == "length"

        except Exception as error:  # noqa: BLE001
            raise OllamaUnavailableError(str(error)) from error

    def chat(self, messages: list) -> str:
        """The whole reply at once (no streaming)."""

        return "".join(self.chat_stream(messages)).strip()
