import threading
import time
from dataclasses import dataclass

from loguru import logger

from torque.conversation.wake_word import match_wake_word
from torque.system.config_service import load_config
from torque.websocket.websocket_service import WebSocketService


@dataclass
class Trigger:
    """What started a conversation."""

    source: str          # "hotkey" | "wake"
    text: str = ""       # what was already said after "Hey Torque"


class AssistantController:
    """
    Owns Torque's behaviour over time.

    A background main loop waits for a trigger - the hotkey, or "Hey Torque"
    heard by the always-on microphone - and then runs a conversation:

        listen -> understand -> (act | search | chat) -> speak -> repeat

    The conversation ends on a goodbye, on silence, or when cancelled
    (hotkey pressed again, or {"type": "cancel"} from the UI).
    """

    MAX_EMPTY_TURNS = 3
    MAX_CONTINUATIONS = 2
    CONTINUATION_TIMEOUT = 4.0
    WAKE_MAX_SECONDS = 10.0       # longer ambient speech is not run through Whisper
    IDLE_RETRY_SECONDS = 3.0
    LEVEL_INTERVAL = 0.05         # seconds between microphone-level messages

    def __init__(self, manager, brain=None, tts=None, conversation=None, chime=None):

        self.manager = manager
        self.config = load_config()

        self.ws = manager.get(WebSocketService)

        if brain is None or tts is None or conversation is None:
            brain, tts, conversation = self._load_components(brain, tts, conversation)

        self.brain = brain
        self.tts = tts
        self.conversation = conversation

        if chime is None and self.config["chime_enabled"] and tts is not None:
            from torque.audio.chime import play_chime as chime

        self._chime = chime

        self.wake_enabled = bool(self.config["wake_word_enabled"])

        self._lock = threading.Lock()                # held during a conversation
        self._cancelled = threading.Event()
        self._activation = threading.Event()         # hotkey / tray / UI asked to start
        self._shutdown = threading.Event()
        self._thread = None
        self._needs_reset = True
        self._state = "idle"
        self._last_level = 0.0

        if self.ws:
            self.ws.set_message_handler(self.handle_message)

        self.conversation.speech.set_level_callback(self._on_level)

        self.idle()

    # ==========================================================
    # START-UP
    # ==========================================================

    def _load_components(self, brain, tts, conversation):
        """
        Load the slow parts at the same time. Whisper, Piper and the brain
        (app scan, LLM check) are independent, so start-up takes as long as
        the slowest one instead of the sum.
        """

        from concurrent.futures import ThreadPoolExecutor

        def make_conversation():
            from torque.audio.speech_service import SpeechService
            from torque.core.conversation_manager import ConversationManager

            return ConversationManager(speech=SpeechService())

        def make_tts():
            from torque.audio.tts_service import TTSService

            service = TTSService()
            service.warm_up()

            return service

        def make_brain():
            from torque.ai.brain import TorqueBrain

            return TorqueBrain()

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="TorqueLoad") as pool:

            futures = {
                "conversation": pool.submit(make_conversation) if conversation is None else None,
                "tts": pool.submit(make_tts) if tts is None and self.config["voice_enabled"] else None,
                "brain": pool.submit(make_brain) if brain is None else None,
            }

            conversation = futures["conversation"].result() if futures["conversation"] else conversation
            tts = futures["tts"].result() if futures["tts"] else tts
            brain = futures["brain"].result() if futures["brain"] else brain

        return brain, tts, conversation

    def start(self):
        """Begin listening for the wake word / hotkey in the background."""

        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._main_loop,
            name="TorqueMain",
            daemon=True,
        )

        self._thread.start()

        if self.wake_enabled:
            logger.info("Listening for 'Hey Torque'.")

    # ==========================================================
    # ENTRY POINTS
    # ==========================================================

    def toggle(self):
        """Hotkey / tray: start a conversation, or cancel the running one."""

        if self.conversation.active:
            self.cancel()
            return

        self._activation.set()

        # Wake the idle listener so it notices.
        self.conversation.speech.interrupt()

        if self._thread is None or not self._thread.is_alive():
            # No main loop (e.g. embedded use): run the conversation directly.
            self._activation.clear()
            self.activate()

    def cancel(self):

        logger.info("Cancelling conversation.")

        self._cancelled.set()

        if self.tts:
            self.tts.stop()

        self.conversation.stop()

    def handle_message(self, message: dict):
        """Messages from the UI over the WebSocket."""

        kind = message.get("type")

        if kind == "cancel":
            self.cancel()

        elif kind == "activate":
            self.toggle()

        elif kind == "text":
            text = str(message.get("text", "")).strip()

            if text:
                self.handle_text(text)

        else:
            logger.debug(f"Ignoring UI message type '{kind}'.")

    def handle_text(self, text: str):
        """One typed turn (no microphone)."""

        if not self._lock.acquire(blocking=False):
            logger.info("Busy; ignoring typed request.")
            return

        self._cancelled.clear()

        try:
            logger.info(f"User (typed): {text}")

            self.conversation.add_user_message(text)

            self.thinking(text)

            self._respond()

        finally:
            self.idle()

            self._needs_reset = True

            self._lock.release()

    def ask_remote(self, text: str) -> str:
        """
        One request from the phone. The reply is returned, not spoken on the
        PC, and the overlay stays quiet. Power actions are refused.
        """

        if not self._lock.acquire(timeout=20):
            return "Torque is busy with a conversation at the PC. Try again in a moment."

        try:
            logger.info("Phone request.")

            self.conversation.add_user_message(text)

            sentences = list(
                self.brain.process_stream(self.conversation.get_history(), remote=True)
            )

            reply = " ".join(sentences).strip() or "Okay."

            self.conversation.add_assistant_message(reply)

            return reply

        except Exception:  # noqa: BLE001
            logger.exception("Phone request failed.")

            return "Something went wrong on my side."

        finally:
            self._needs_reset = True

            self._lock.release()

    def activate(self, first_text=None):
        """Run one conversation. `first_text` is a request already heard."""

        if not self._lock.acquire(blocking=False):
            return

        self._cancelled.clear()

        try:
            self._conversation_loop(first_text)

        finally:
            self.idle()

            self.conversation.stop()

            self._needs_reset = True

            self._lock.release()

    def shutdown(self):

        self._shutdown.set()

        self.cancel()

        self.conversation.speech.interrupt()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

        self.brain.shutdown()

        close = getattr(self.conversation.speech, "close", None)

        if close:
            close()

    # ==========================================================
    # MAIN LOOP
    # ==========================================================

    def _main_loop(self):

        while not self._shutdown.is_set():

            try:
                trigger = self._wait_for_trigger()

                if trigger is None or self._shutdown.is_set():
                    continue

                logger.info(f"Triggered by {trigger.source}.")

                self.activate(first_text=trigger.text)

            except Exception:  # noqa: BLE001
                logger.exception("Main loop error.")

                self._shutdown.wait(self.IDLE_RETRY_SECONDS)

    def _wait_for_trigger(self):
        """
        Block until something should start a conversation. Returns a
        Trigger, or None to simply run the loop again.
        """

        if self._activation.is_set():
            self._activation.clear()
            return Trigger("hotkey")

        if not self.wake_enabled:
            self._activation.wait(0.5)
            return None

        speech = self.conversation.speech

        if self._needs_reset:
            speech.reset()
            self._needs_reset = False

        text = speech.listen(timeout=None, max_seconds=self.WAKE_MAX_SECONDS)

        if not text:
            return None

        if self._lock.locked():
            return None           # a typed request is being handled

        match = match_wake_word(text)

        if not match.matched:
            logger.debug("Ignored speech that was not for Torque.")
            return None

        return Trigger("wake", match.remainder)

    # ==========================================================
    # CONVERSATION LOOP
    # ==========================================================

    def _conversation_loop(self, first_text=None):

        self.conversation.start()

        pending = first_text or None

        if pending is None:
            self.listening()
            self._play_chime()

        empty_turns = 0
        first_turn = True

        while self.conversation.active:

            if pending is not None:
                text, pending = pending, None

            else:
                self.listening()

                timeout = (
                    self.config["listen_timeout"]
                    if first_turn
                    else self.config["followup_timeout"]
                )

                text = self.conversation.listen(timeout=timeout)

                # Silence (or cancelled): end the conversation quietly.
                if text is None:
                    break

                # Speech detected but nothing recognised (noise).
                if not text:
                    empty_turns += 1

                    if empty_turns >= self.MAX_EMPTY_TURNS:
                        break

                    continue

                text = self._complete_sentence(text)

            empty_turns = 0
            first_turn = False

            logger.info(f"User: {text}")

            if self.conversation.should_stop(text):

                self.speaking("Alright, see you later.")

                self._speak("Alright, see you later.")

                break

            # A bare "yes" is chatter, unless Torque just asked to confirm something.
            if (
                self.brain.conversation_policy.is_acknowledgement(text)
                and not getattr(self.brain, "awaiting_confirmation", False)
            ):
                continue

            self.conversation.add_user_message(text)

            self.thinking(text)

            self._respond()

    def _complete_sentence(self, text: str) -> str:
        """
        If the user trailed off mid-sentence ("open chrome and..."), listen
        once more and join the pieces.
        """

        policy = self.brain.conversation_policy

        for _ in range(self.MAX_CONTINUATIONS):

            if not policy.is_incomplete(text):
                break

            more = self.conversation.listen(
                timeout=self.CONTINUATION_TIMEOUT,
                flush=False,         # their next words may already be buffered
            )

            if not more:
                break

            text = f"{text} {more}"

        return text

    def _respond(self):
        """
        Produce and speak the reply. The brain yields sentences as they are
        ready, and the speech engine starts on the first one while the rest
        is still being generated.
        """

        spoken = []

        def sentences():

            try:
                for sentence in self.brain.process_stream(
                    self.conversation.get_history(),
                    on_status=self._send,
                ):
                    if self._cancelled.is_set():
                        return

                    spoken.append(sentence)

                    self.speaking(" ".join(spoken))

                    yield sentence

            except Exception:  # noqa: BLE001
                logger.exception("Brain failed.")

                apology = "Something went wrong on my side."

                spoken.append(apology)

                self.speaking(" ".join(spoken))

                yield apology

        self._speak(sentences())

        if spoken and not self._cancelled.is_set():

            reply = " ".join(spoken)

            self.conversation.add_assistant_message(reply)

            logger.info(f"Torque: {reply}")

    def _speak(self, speech):
        """Speak a string or an iterable of sentences (always consumed)."""

        if not self.tts or self._cancelled.is_set():

            if not isinstance(speech, str):
                for _ in speech:         # still drive the brain so the text is shown
                    pass

            return

        try:
            self.tts.speak(speech)

        except Exception:  # noqa: BLE001
            logger.exception("Text-to-speech failed.")

    def _play_chime(self):

        if self._chime:

            try:
                self._chime("wake")
            except Exception:  # noqa: BLE001
                logger.debug("Chime failed.", exc_info=True)

    # ==========================================================
    # UI STATE
    # ==========================================================

    def listening(self):
        self._send("listening", "Listening...")

    def thinking(self, heard=None):

        if heard:
            self._send("thinking", "Thinking...", heard=heard)
        else:
            self._send("thinking", "Thinking...")

    def searching(self):
        self._send("searching", "Searching the web...")

    def speaking(self, text):
        self._send("speaking", text)

    def idle(self):
        self._send("idle", "")

    def _send(self, state, message, **extra):

        self._state = state

        if self.ws:
            self.ws.send({"state": state, "message": message, **extra})

    def _on_level(self, rms: float):
        """Microphone loudness for the UI's listening animation."""

        if self._state != "listening" or not self.ws:
            return

        now = time.monotonic()

        if now - self._last_level < self.LEVEL_INTERVAL:
            return

        self._last_level = now

        self.ws.send_level(min(1.0, (rms * 12) ** 0.7))
