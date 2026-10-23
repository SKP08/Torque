import re
from datetime import datetime

from loguru import logger

from torque.ai.context_builder import ContextBuilder
from torque.ai.ollama_service import OllamaService, OllamaUnavailableError
from torque.conversation.conversation_policy import ConversationPolicy
from torque.memory.memory_retriever import MemoryRetriever
from torque.memory.memory_service import MemoryService
from torque.memory.memory_store import MemoryStore
from torque.system.background_worker import BackgroundWorker
from torque.system.system_router import SystemRouter
from torque.utils.text import to_speech
from torque.web.search_router import SearchRouter

_TIME = re.compile(
    r"\bwhat(?:'s| is)?(?: the)?(?: current)? time(?! in\b| at\b| zone\b| for\b)"
    r"|\bwhat time is it\b|\btell me the time\b|\bcurrent time\b(?! in\b)",
    re.IGNORECASE,
)

_DATE = re.compile(
    r"\bwhat(?:'s| is)?(?: the)?(?: today'?s)? date\b(?! of\b)"
    r"|\bwhat day is (?:it|today)\b|\bwhat is today\b|\btoday'?s date\b",
    re.IGNORECASE,
)


class TorqueBrain:
    """
    Turns what the user said into a reply, in a fixed order:

        1. quick local answers (time / date)
        2. app commands (open / close)
        3. web search
        4. the local LLM, with memories

    Every collaborator can be injected, which keeps routing testable.
    """

    def __init__(
        self,
        llm=None,
        web=None,
        memory=None,
        launcher=None,
        worker=None,
        policy=None,
        system_router=None,
        search_router=None,
        context=None,
    ):

        logger.info("Initializing Torque Brain...")

        store = None

        if memory is None or context is None:
            store = MemoryStore()

        self.memory = memory or MemoryService(store=store)
        self.context = context or ContextBuilder(MemoryRetriever(store))

        self.llm = llm or OllamaService()
        self.worker = worker or BackgroundWorker()

        if web is None:
            from torque.web.web_service import WebService

            web = WebService()

        self.web = web

        if launcher is None:
            from torque.system.app_launcher import AppLauncher

            launcher = AppLauncher()

        self.app_launcher = launcher

        self.router = search_router or SearchRouter()
        self.system_router = system_router or SystemRouter()
        self.conversation_policy = policy or ConversationPolicy()

        logger.success("Torque Brain ready.")

    # ==========================================================
    # SYSTEM COMMANDS
    # ==========================================================

    def _execute_command(self, command: dict) -> str | None:
        """
        Run one open/close command. Returns what to say, or None when the
        phrase should not be treated as a command at all (a "weak" verb
        such as "start talking" that doesn't name a real app).
        """

        action = command["action"]
        target = command["target"]

        logger.info(f"System command: {action} '{target}'")

        if action == "open":
            result = self.app_launcher.launch(target)

        elif action == "close":
            result = self.app_launcher.close(target)

        else:
            return None

        if not result.success and not command.get("explicit", True):
            # "start talking to me" -> no such app -> just chat.
            if "couldn't find" in result.message:
                return None

        return result.message

    def _process_system_commands(self, text: str) -> str | None:

        system = self.system_router.route(text)

        if not system:
            return None

        if system["action"] != "sequence":
            return self._execute_command(system)

        results = []

        for command in system["commands"]:

            reply = self._execute_command(command)

            if reply:
                results.append(reply)

        return " ".join(results) or None

    # ==========================================================
    # QUICK LOCAL ANSWERS
    # ==========================================================

    @staticmethod
    def _quick_answer(text: str) -> str | None:

        now = datetime.now()

        if _TIME.search(text):
            return f"It's {now.strftime('%I:%M %p').lstrip('0')}."

        if _DATE.search(text):
            return f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."

        return None

    # ==========================================================
    # MAIN
    # ==========================================================

    def process(self, history: list, on_status=None) -> str | None:
        """
        Returns the reply to speak, or None if there is nothing to say.

        on_status(state, message) is called when Torque starts doing
        something the user should hear about (e.g. "searching").
        """

        logger.info("Brain processing request...")

        last_user = next(
            (
                msg["content"].strip()
                for msg in reversed(history)
                if msg["role"] == "user"
            ),
            "",
        )

        if not last_user:
            return "I didn't catch that."

        policy = self.conversation_policy.analyze_input(last_user)

        if policy["intent"] in ("empty", "acknowledgement"):
            return None

        logger.info(f"Conversation intent: {policy['intent']}")

        # 1. Quick local answers.
        quick = self._quick_answer(last_user)

        if quick:
            return quick

        # 2. App commands (routed on the corrected, normalised text).
        reply = self._process_system_commands(policy["effective_text"])

        if reply:
            return reply

        # 3. Web search (on the user's own words).
        if self.router.needs_web(last_user):

            logger.info("Using Web Search...")

            if on_status and self.web.enabled:
                on_status("searching", self.router.announcement(last_user))

            result = self.web.search(last_user)

            self._remember(last_user)

            return to_speech(result.answer) or "I couldn't find anything on that."

        # 4. The language model.
        messages = self.context.build(history)

        try:
            response = self.llm.chat(messages)

        except OllamaUnavailableError:
            logger.exception("LLM unavailable.")

            return "I can't reach my language model. Is Ollama running?"

        self._remember(last_user)

        return response

    def _remember(self, text: str):

        if self.memory.should_extract(text):

            self.worker.submit(
                "Memory Extraction",
                self.memory.extract,
                text,
            )

    # ==========================================================
    # SHUTDOWN
    # ==========================================================

    def shutdown(self):

        self.worker.shutdown()
