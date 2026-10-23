from torque.ai.system_prompt import build_system_prompt
from torque.system.config_service import load_config
from torque.memory.memory_retriever import MemoryRetriever


class ContextBuilder:

    def __init__(self, retriever=None):

        self.memory = retriever or MemoryRetriever()

        config = load_config()

        self.system_prompt = build_system_prompt(config["persona"], config["user_title"])

    def build(self, history: list):

        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

        memories = self.memory.retrieve(history)

        if memories:

            memory_text = "Known facts about the user:\n"

            for memory in memories:
                memory_text += f"- {memory['key']}: {memory['value']}\n"

            messages.append({"role": "system", "content": memory_text})

        messages.extend(history)

        return messages
