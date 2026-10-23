import json
import re
from datetime import UTC, datetime

from loguru import logger

from torque.memory.memory_prompt import MEMORY_PROMPT
from torque.memory.memory_store import MemoryStore
from torque.memory.memory_types import Memory

# Cheap gate so the LLM is only asked when a message sounds like the user
# is telling us something about themselves.
_PERSONAL = re.compile(
    r"\b(?:my|i am|i'm|i live|i like|i love|i prefer|i have|i work|i study|"
    r"i use|i own|i was born|i hate|i don't like|i do not like|call me|"
    r"remember)\b",
    re.IGNORECASE,
)

_QUESTION_START = re.compile(
    r"^(?:what|what's|whats|who|when|where|which|how|do you|can you|"
    r"could you|is|are)\b",
    re.IGNORECASE,
)


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


class MemoryService:

    def __init__(self, store=None, model=None, chat=None):

        self.store = store or MemoryStore()

        if model is None:
            from torque.system.config_service import load_config

            model = load_config()["llm_model"]

        self.model = model

        # Injectable for tests; defaults to Ollama.
        self._chat = chat

    def should_extract(self, text: str) -> bool:

        text = (text or "").strip()

        if len(text.split()) < 3:
            return False

        if _QUESTION_START.match(text):
            return False

        return bool(_PERSONAL.search(text))

    def _call_llm(self, text: str) -> str:

        chat = self._chat

        if chat is None:
            from ollama import chat

        response = chat(
            model=self.model,
            messages=[
                {"role": "system", "content": MEMORY_PROMPT},
                {"role": "user", "content": text},
            ],
            options={"temperature": 0, "num_predict": 100},
            format="json",
        )

        return response["message"]["content"]

    def extract(self, text: str):

        if not self.should_extract(text):
            return

        try:
            data = json.loads(self._call_llm(text))

        except json.JSONDecodeError:
            logger.warning("Memory extraction returned invalid JSON.")
            return

        except Exception:  # noqa: BLE001
            logger.exception("Memory extraction failed.")
            return

        if not isinstance(data, dict) or not data.get("save"):
            return

        key = normalize_key(data.get("key", ""))
        value = str(data.get("value", "")).strip()[:200]
        category = str(data.get("category") or "other").strip().lower() or "other"

        if not key or not value:
            logger.warning(f"Memory extraction missing key/value: {data}")
            return

        self.remember(key=key, value=value, category=category)

    def remember(self, key: str, value: str, category: str = "other"):

        now = datetime.now(UTC)

        self.store.save(
            Memory(
                key=key,
                value=value,
                category=category,
                created_at=now,
                updated_at=now,
            )
        )

        logger.success(f"Saved memory: {key} = {value}")

    def forget(self, key: str):

        self.store.delete(normalize_key(key))
