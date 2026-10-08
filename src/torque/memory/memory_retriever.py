from torque.memory.memory_store import MemoryStore


class MemoryRetriever:

    def __init__(self):

        self.store = MemoryStore()

    def retrieve(self, history: list) -> list:

        memories = []

        user_message = ""

        for message in reversed(history):

            if message["role"] == "user":

                user_message = message["content"].lower()

                break

        all_memories = self.store.get_all()

        for key, value, category in all_memories:

            words = key.lower().replace("_", " ").split()

            if any(word in user_message for word in words):

                memories.append(
                    {
                        "key": key,
                        "value": value,
                        "category": category,
                    }
                )

        return memories