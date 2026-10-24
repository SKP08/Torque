import re
from collections.abc import Iterator
from datetime import datetime

from loguru import logger

from torque.agent.router import wants_agent, wants_browser
from torque.hud.entities import is_info_question
from torque.ai.context_builder import ContextBuilder
from torque.ai.ollama_service import OllamaService, OllamaUnavailableError
from torque.conversation.conversation_policy import ConversationPolicy
from torque.memory.memory_retriever import MemoryRetriever
from torque.memory.memory_service import MemoryService
from torque.memory.memory_store import MemoryStore
from torque.system.background_worker import BackgroundWorker
from torque.screen.screen_assistant import is_screen_request
from torque.system.config_service import load_config
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


def _network_view(config):
    """A callable that builds the network-globe payload (None until the GeoIP file exists)."""

    from torque.network.geoip import GeoIP
    from torque.network.live import network_snapshot

    geoip = GeoIP()
    home = config.get("home_location")

    def view():
        nonlocal geoip

        if not geoip.available:
            geoip = GeoIP()                  # picked up after the user downloads it

        return network_snapshot(geoip, home=home) if geoip.available else None

    return view


class TorqueBrain:
    """
    Turns what the user said into a reply, in a fixed order:

        1. quick local answers (time / date)
        2. PC-control skills (volume, media, screenshot, power...)
        3. screen questions ("what's this error?")
        4. multi-step file tasks (tool-calling agent)
        5. app commands (open / close)
        6. web search
        7. the local LLM, with memories

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
        skills=None,
        screen=None,
        agent=None,
        info=None,
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

        if skills is None:
            skills = self._default_skills()

        self.skills = skills

        if screen is None and load_config()["screen_enabled"]:
            from torque.screen.screen_assistant import ScreenAssistant

            screen = ScreenAssistant(self.llm)

        self.screen = screen or None

        if agent is None:
            from torque.agent.model import build_agent

            agent = build_agent(load_config())

        self.agent = agent or None

        if info is None and load_config()["hud_enabled"]:
            from torque.hud.info import InfoService
            from torque.hud.wiki import WikiClient
            from torque.paths import HUD_CACHE

            info = InfoService(WikiClient(HUD_CACHE))

        self.info = info or None

        self.router = search_router or SearchRouter()
        self.system_router = system_router or SystemRouter()
        self.conversation_policy = policy or ConversationPolicy()

        logger.success("Torque Brain ready.")

    # ==========================================================
    # PC-CONTROL SKILLS
    # ==========================================================

    @staticmethod
    def _default_skills():

        config = load_config()

        from torque.skills.registry import SkillRegistry

        skills = []

        if config["pc_control_enabled"]:
            from torque.skills.backend import default_backend
            from torque.skills.pc_control import build_pc_skills

            skills += build_pc_skills(default_backend())

        if config["hud_enabled"]:
            from torque.skills.hud_skills import build_hud_skills

            from torque.timers.store import default_store

            skills += build_hud_skills(timers=default_store() if config["timers_enabled"] else None,
                                       network_fn=_network_view(config))

        if config.get("desktop_control_enabled"):
            try:
                from torque.desktop.backend import WindowsDesktop
                from torque.desktop.finder import ScreenFinder
                from torque.skills.desktop_skills import build_desktop_skills

                skills += build_desktop_skills(ScreenFinder(), WindowsDesktop())
            except NotImplementedError:
                logger.warning("Desktop control only works on Windows; leaving it off.")

        if config["timers_enabled"]:
            from torque.skills.timer_skills import build_timer_skills
            from torque.timers.store import default_store

            skills += build_timer_skills(default_store())

        if config["security_skills_enabled"]:
            from torque.skills.security import build_security_skills

            skills += build_security_skills()

        return SkillRegistry(skills) if skills else None

    @property
    def awaiting_confirmation(self) -> bool:
        """True while Torque has asked "are you sure?" and is waiting."""

        return bool(self.skills and self.skills.awaiting_confirmation)

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

    def process_stream(self, history: list, on_status=None, remote: bool = False, on_hud=None) -> Iterator[str]:
        """
        Yield the reply one speakable sentence at a time (nothing if there is
        nothing to say).

        on_status(state, message) reports UI state changes, e.g. "searching".
        on_hud(payload) shows an on-screen panel (info, status, or {"kind": "clear"}).
        remote=True marks a request from the phone: power actions are refused.
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

        # A pending "are you sure?" gets the very next sentence, including a
        # bare "yes" that would otherwise be ignored as an acknowledgement.
        if self.skills and self.skills.awaiting_confirmation and not remote:
            reply = self.skills.handle(last_user)

            if reply:
                yield reply
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

        # 2. PC control: volume, media, windows, screenshot, power...
        if self.skills:
            reply = self.skills.handle(last_user, allow_confirm=not remote, hud=None if remote else on_hud)

            if reply:
                yield from split_sentences(reply)
                return

        # 3. "What's this error?" - look at the screen.
        if self.screen and is_screen_request(last_user):

            if on_status:
                on_status("thinking", "Looking at your screen...")

            yield from self.screen.answer(last_user)

            return

        # 4. Multi-step file tasks: the tool-calling agent.
        if self.agent and (wants_agent(last_user) or wants_browser(last_user)):
            yield from self._run_agent(last_user, on_status)

            return

        # 5. App commands (routed on the corrected, normalised text).
        reply = self._process_system_commands(policy["effective_text"])

        if reply:
            yield from split_sentences(reply)
            return

        # 6. Web search (on the user's own words).
        if self.router.needs_web(last_user):

            logger.info("Using Web Search...")

            if self.web.enabled:
                # Said aloud while the search runs.
                yield self.router.announcement(last_user)

                if on_status:
                    on_status("searching", "Searching the web...")

            result = self.web.search(last_user)

            self._remember(last_user)

            yield from self._with_hud(
                iter(split_sentences(to_speech(result.answer) or "I couldn't find anything on that.")),
                last_user, on_hud, remote,
            )

            return

        # 7. The language model, streamed sentence by sentence.
        yield from self._with_hud(self._chat(history, last_user), last_user, on_hud, remote)

    def _with_hud(self, sentences, question, on_hud, remote) -> Iterator[str]:
        """
        Pass sentences through unchanged; for factual questions also build
        and show the info panels from the finished answer, in the background
        so speech is never delayed.
        """

        show = bool(self.info and on_hud and not remote and is_info_question(question))

        if show:
            self.worker.submit("HUD prefetch", self.info.prefetch, question)

        spoken = []

        for sentence in sentences:
            spoken.append(sentence)
            yield sentence

        if show and spoken:
            self.worker.submit("HUD panels", self._show_info, question, " ".join(spoken), on_hud)

    def _show_info(self, question, answer, on_hud):

        payload = self.info.build(question, answer)

        if payload:
            on_hud(payload)

    def _run_agent(self, request: str, on_status) -> Iterator[str]:

        yield "On it."

        def progress(step):

            if on_status:
                on_status("thinking", f"{step}...")

        try:
            result = self.agent.run(request, on_step=progress)

        except OllamaUnavailableError:
            yield (
                "I can't reach the agent model. Make sure Ollama is running and that you "
                "have pulled it, for example with ollama pull qwen3:4b."
            )
            return

        except Exception:  # noqa: BLE001
            logger.exception("Agent failed.")
            yield "Something went wrong while I was working on that."
            return

        yield from split_sentences(to_speech(result.reply) or "Done.")

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

        if self.agent:
            getattr(self.agent, "close", lambda: None)()

        self.worker.shutdown()
