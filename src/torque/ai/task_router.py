from torque.web.search_router import SearchRouter


class TaskRouter:

    def __init__(self):

        self.search_router = SearchRouter()

    def route(self, history: list) -> str:

        last_user = next(
            (
                msg["content"]
                for msg in reversed(history)
                if msg["role"] == "user"
            ),
            "",
        )

        if self.search_router.needs_web(last_user):
            return "web"

        return "llm"