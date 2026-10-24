from loguru import logger

from torque.ai.ollama_service import OllamaUnavailableError


class AgentModel:
    """The agent's chat call: a local Ollama model with tool calling."""

    def __init__(self, model, num_ctx=4096, chat=None):

        self.model = model
        self.num_ctx = num_ctx
        self._chat = chat

    def __call__(self, messages, tools) -> dict:

        chat = self._chat

        if chat is None:
            from ollama import chat

        options = {"temperature": 0.1, "num_ctx": self.num_ctx, "num_predict": 300}

        try:
            try:
                # Thinking mode makes every step much slower on a small GPU.
                response = chat(model=self.model, messages=messages, tools=tools,
                                options=options, think=False, keep_alive="10m")
            except TypeError:
                response = chat(model=self.model, messages=messages, tools=tools,
                                options=options, keep_alive="10m")

        except Exception as error:  # noqa: BLE001
            logger.warning(f"Agent model call failed: {error}")
            raise OllamaUnavailableError(str(error)) from error

        message = response["message"] if isinstance(response, dict) else response.message

        def get(obj, key, default=None):
            return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

        calls = []

        for call in get(message, "tool_calls") or []:

            function = get(call, "function")

            calls.append({"function": {
                "name": get(function, "name", ""),
                "arguments": dict(get(function, "arguments") or {}),
            }})

        return {"content": get(message, "content", "") or "", "tool_calls": calls}


def build_agent(config):
    """The agent with file tools (and browser tools if enabled), or None if disabled."""

    if not config["agent_enabled"]:
        return None

    from torque.agent.agent import Agent
    from torque.agent.file_tools import FileTools, build_file_tools

    tools = build_file_tools(FileTools())
    rules = ""
    num_ctx = 4096

    if config.get("browser_enabled"):
        from torque.agent.browser_tools import (
            BROWSER_RULES, BrowserTools, PlaywrightBackend, build_browser_tools,
        )
        from torque.paths import DATA_DIR

        backend = PlaywrightBackend(DATA_DIR / "browser_profile", channel=config["browser_channel"],
                                    headless=config["browser_headless"])
        tools += build_browser_tools(BrowserTools(backend))
        rules = BROWSER_RULES
        num_ctx = 8192

    agent = Agent(AgentModel(config["agent_model"], num_ctx=num_ctx), tools,
                  max_steps=config["agent_max_steps"], extra_rules=rules)

    if config.get("browser_enabled"):
        agent.closers.append(backend.close)

    return agent
