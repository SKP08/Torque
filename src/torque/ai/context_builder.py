from torque.ai.system_prompt import SYSTEM_PROMPT
from torque.memory.memory_retriever import MemoryRetriever


class ContextBuilder:

    def __init__(self):

        self.memory = MemoryRetriever()

    def build(self, history: list):

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        memories = self.memory.retrieve(history)

        if memories:

            memory_text = "Known facts about the user:\n"

            for memory in memories:

                memory_text += (
                    f"- {memory['key']}: {memory['value']}\n"
                )

            messages.append(
                {
                    "role": "system",
                    "content": memory_text,
                }
            )

        messages.extend(history)

        return messages