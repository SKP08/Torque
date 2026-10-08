from torque.memory.memory_service import MemoryService

memory = MemoryService()

memory.remember(
    key="favorite_language",
    value="Python",
    category="preference",
)

memory.remember(
    key="favorite_movie",
    value="Interstellar",
    category="preference",
)

memory.remember(
    key="laptop",
    value="ASUS TUF A17",
    category="device",
)

print("Memory inserted successfully.")