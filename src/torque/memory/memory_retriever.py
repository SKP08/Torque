import re

from torque.memory.memory_store import MemoryStore

_STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "do", "does", "did", "i", "me",
    "my", "you", "your", "what", "whats", "what's", "which", "who", "how",
    "to", "of", "in", "on", "at", "and", "or", "can", "it", "this", "that",
    "have", "has", "for", "with", "about", "tell", "please",
}

# Words that appear in many keys and say nothing about the topic.
_KEY_NOISE = {"favorite", "favourite", "user", "my", "the"}

_RECALL = re.compile(
    r"\b(?:about me|know about me|remember about me|what do you remember|"
    r"my preferences|my details)\b",
    re.IGNORECASE,
)


def _tokens(text: str) -> set[str]:

    words = re.findall(r"[a-z0-9]+", (text or "").lower())

    # Crude singularisation: "laptops" matches "laptop".
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


class MemoryRetriever:

    MAX_RESULTS = 5

    def __init__(self, store=None):

        self.store = store or MemoryStore()

    def retrieve(self, history: list) -> list:

        user_message = ""

        for message in reversed(history):

            if message["role"] == "user":
                user_message = message["content"]
                break

        all_memories = self.store.get_all()

        if _RECALL.search(user_message):
            return [
                {"key": k, "value": v, "category": c}
                for k, v, c in all_memories[: self.MAX_RESULTS + 3]
            ]

        message_tokens = _tokens(user_message) - _STOPWORDS

        scored = []

        for key, value, category in all_memories:

            key_tokens = _tokens(key.replace("_", " ")) - _KEY_NOISE - _STOPWORDS
            value_tokens = _tokens(value) - _STOPWORDS

            score = 2 * len(key_tokens & message_tokens) + len(value_tokens & message_tokens)

            if score > 0:
                scored.append(
                    (score, {"key": key, "value": value, "category": category})
                )

        scored.sort(key=lambda item: item[0], reverse=True)

        return [memory for _, memory in scored[: self.MAX_RESULTS]]
