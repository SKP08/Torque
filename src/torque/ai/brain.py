import re
from collections.abc import Iterator
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
from torque.utils.text import SentenceChunker, split_sentences, to_speech
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

    The reply is produced as a stream of sentences (process_stream) so the
    first one can be spoken while the rest is still being generated.

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

        warm = llm is None

        self.llm = llm or OllamaService()
        self.worker = worker or BackgroundWorker()

        if warm:
            self.llm.warm_up()

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

    def process_stream(self, history: list, on_status=None) -> Iterator[str]:
        """
        Yield the reply one speakable sentence at a time (nothing if there is
        nothing to say).

        on_status(state, message) reports UI state changes, e.g. "searching".
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
            yield "I didn't catch that."
            return

        policy = self.conversation_policy.analyze_input(last_user)

        if policy["intent"] in ("empty", "acknowledgement"):
            return

        logger.info(f"Conversation intent: {policy['intent']}")

        # 1. Quick local answers.
        quick = self._quick_answer(last_user)

        if quick:
            yield quick
            return

        # 2. App commands (routed on the corrected, normalised text).
        reply = self._process_system_commands(policy["effective_text"])

        if reply:
            yield from split_sentences(reply)
            return

        # 3. Web search (on the user's own words).
        if self.router.needs_web(last_user):

            logger.info("Using Web Search...")

            if self.web.enabled:
                # Said aloud while the search runs.
                yield self.router.announcement(last_user)

                if on_status:
                    on_status("searching", "Searching the web...")

            result = self.web.search(last_user)

            self._remember(last_user)

            yield from split_sentences(
                to_speech(result.answer) or "I couldn't find anything on that."
            )

            return

        # 4. The language model, streamed sentence by sentence.
        yield from self._chat(history, last_user)

    def _chat(self, history: list, last_user: str) -> Iterator[str]:

        messages = self.context.build(history)

        chunker = SentenceChunker()

        try:
            for piece in self.llm.chat_stream(messages):
                yield from chunker.feed(piece)

        except OllamaUnavailableError:
            logger.exception("LLM unavailable.")

            if not chunker.emitted:
                yield "I can't reach my language model. Is Ollama running?"

            return

        yield from chunker.finish(truncated=getattr(self.llm, "truncated", False))

        self._remember(last_user)

    def process(self, history: list, on_status=None) -> str | None:
        """The whole reply as one string (None if there is nothing to say)."""

        reply = " ".join(self.process_stream(history, on_status=on_status)).strip()

        return reply or None

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
