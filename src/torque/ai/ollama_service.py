from loguru import logger
from ollama import chat


class OllamaService:

    def __init__(self):

        self.model = "qwen2.5:3b"

        logger.success(f"Ollama model: {self.model}")

    def chat(self, messages: list) -> str:

        last_user = next(
            (
                msg["content"]
                for msg in reversed(messages)
                if msg["role"] == "user"
            ),
            "",
        )

        logger.info(f"User: {last_user}")

        response = chat(
            model=self.model,
            keep_alive="30m",
            options={
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 80,
                "num_ctx": 2048,
            },
            messages=messages,
        )

        answer = response["message"]["content"].strip()

        logger.success(f"Torque: {answer}")

        return answer