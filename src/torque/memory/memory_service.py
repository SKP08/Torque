import json
from datetime import UTC, datetime

from loguru import logger
from ollama import chat

from torque.memory.memory_prompt import MEMORY_PROMPT
from torque.memory.memory_store import MemoryStore
from torque.memory.memory_types import Memory


class MemoryService:

    def __init__(self):

        self.store = MemoryStore()
        self.model = "qwen2.5:3b"

    def extract(self, text: str):

        response = chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": MEMORY_PROMPT,
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            options={
                "temperature": 0,   
                "num_predict": 80,
            },
            format="json",
        )

        try:

            data = json.loads(
                response["message"]["content"]
            )

        except json.JSONDecodeError:

            logger.warning("Memory extraction failed.")

            return

        if not data.get("save"):

            return

        self.remember(
            key=data["key"],
            value=data["value"],
            category=data["category"],
        )

    def remember(
        self,
        key: str,
        value: str,
        category: str,
    ):

        now = datetime.now(UTC)

        memory = Memory(
            key=key,
            value=value,
            category=category,
            created_at=now,
            updated_at=now,
        )

        self.store.save(memory)

        logger.success(f"Saved memory: {key} = {value}")