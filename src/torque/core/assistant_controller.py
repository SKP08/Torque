import threading
import time
from dataclasses import dataclass

from loguru import logger

from torque.alerts import bus as alert_bus
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

    def __init__(self, manager, brain=None, tts=None, conversation=None, chime=None, barge_in=None, voice_gate=None, journal=None):

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
        self._watcher = None
        self._pending_speech = []
        self._barge = None
        self._barged = False
        self._voice_gate = None
        self._journal = journal
        self._last_digest = None
        self._needs_reset = True
        self._state = "idle"
        self._last_level = 0.0

        self._setup_barge_in(barge_in)

        if voice_gate is not None:
            self._voice_gate = voice_gate
        elif self.config.get("voice_lock_enabled"):
            from torque.audio.speaker import load_gate

            self._voice_gate = load_gate(self.config)

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

        alert_bus.set_announcer(self.announce)

        self._thread = threading.Thread(
            target=self._main_loop,
            name="TorqueMain",
            daemon=True,
        )

        self._thread.start()

        self._start_journal()
        self._start_alerts()

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

        elif kind == "dismiss":
            self._send_hud({"kind": "clear"})

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

        if self._watcher:
            self._watcher.stop()

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

        if self._voice_gate is not None:
            audio = getattr(getattr(speech, "microphone", None), "last_audio", None)

            if not self._voice_gate.accepts(audio):
                logger.info("Wake word ignored: not the enrolled voice.")
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

                text = self.conversation.listen(timeout=timeout, **self._barge_listen())

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
                    on_hud=self._send_hud,
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

            self._record_turn(reply)

    def _speak(self, speech):
        """Speak a string or an iterable of sentences (always consumed)."""

        if not self.tts or self._cancelled.is_set():

            if not isinstance(speech, str):
                for _ in speech:         # still drive the brain so the text is shown
                    pass

            return

        if self._barge:
            self._barge.arm(self._on_barge)

        try:
            self.tts.speak(speech)

        except Exception:  # noqa: BLE001
            logger.exception("Text-to-speech failed.")

        finally:
            if self._barge:
                self._barge.disarm()

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

    # ==========================================================
    # JOURNAL (what we did today, summarised overnight)
    # ==========================================================

    DIGEST_EVERY = 1800.0           # seconds between "any finished days to summarise?" checks

    def _start_journal(self):
        if self._journal is None and self.config.get("journal_enabled", True):
            try:
                from torque.memory.journal import default_journal

                self._journal = default_journal()
            except Exception:  # noqa: BLE001
                logger.exception("Journal unavailable.")

    def _record_turn(self, reply: str):
        if not self._journal:
            return

        user = next((m["content"] for m in reversed(self.conversation.get_history()) if m["role"] == "user"), "")

        try:
            self._journal.record(user, reply)
        except Exception:  # noqa: BLE001
            logger.exception("Could not write to the journal.")

    def _maybe_digest(self):
        """Quietly summarise finished days with the local model, never during a conversation."""

        if not self._journal or (self._last_digest is not None
                                 and time.monotonic() - self._last_digest < self.DIGEST_EVERY):
            return

        if self._lock.locked():
            return

        self._last_digest = time.monotonic()

        llm = getattr(getattr(self.brain, "llm", None), "chat", None)

        if llm is None:
            return

        threading.Thread(target=self._journal.summarise_missing, args=(llm,),
                         name="TorqueDigest", daemon=True).start()

    # ==========================================================
    # BARGE-IN
    # ==========================================================

    def _setup_barge_in(self, barge):
        """Let the user interrupt Torque by talking (off unless barge_in_enabled)."""

        microphone = getattr(self.conversation.speech, "microphone", None)

        if barge is None:
            if not self.config.get("barge_in_enabled") or not self.tts or microphone is None:
                return

            try:
                from torque.audio.bargein import BargeIn

                barge = BargeIn()

            except Exception:  # noqa: BLE001
                logger.exception("Barge-in unavailable.")
                return

        self._barge = barge

        if self.tts is not None:
            self.tts.tap = barge.tap

        if microphone is not None:
            microphone.on_block = barge.feed

        logger.info("Barge-in on: you can interrupt Torque by talking.")

    def _on_barge(self):
        """Called from the audio thread the moment the user starts talking over Torque."""

        logger.info("Barge-in.")

        self._barged = True

        try:
            self.tts.stop()
        except Exception:  # noqa: BLE001
            logger.debug("Could not stop speech.", exc_info=True)

    def _barge_listen(self) -> dict:
        """listen() arguments after an interruption: keep what was heard instead of flushing it."""

        if not self._barged or not self._barge:
            return {}

        self._barged = False

        return {"flush": False, "preroll": self._barge.take_preroll()}

    # ==========================================================
    # TIMERS AND ALERTS
    # ==========================================================

    def _start_alerts(self):
        """Run the timer / alert watcher (timers fire even if monitors are off)."""

        if self._watcher or not (self.config["timers_enabled"] or self.config["alerts_enabled"] or self._journal):
            return

        from torque.alerts.monitors import AlertMonitor
        from torque.alerts.watcher import AlertWatcher
        from torque.hud.status import system_status
        from torque.timers.store import default_store

        monitor = None

        if self.config["alerts_enabled"]:
            from torque.skills.security import PsutilProbe

            from torque.hud.status import NetworkRate

            probe = PsutilProbe()
            rate = NetworkRate()

            monitor = AlertMonitor(
                lambda: system_status(probe=probe, rate=rate, blocking=False),
                probe.listening_ports,
                categories=self.config["alert_categories"],
            )

        def tick():
            self._flush_speech()
            self._maybe_digest()

        self._watcher = AlertWatcher(default_store(), self.announce, monitor, on_tick=tick)
        self._watcher.start()

    def announce(self, message: str, severity: str = "info", speak: bool = True):
        """Show a toast and (when allowed) say it, without interrupting a conversation."""

        self._send_hud({"kind": "alert", "message": message, "severity": severity, "hold": 8})

        if speak and self.config.get("alert_speech", True) and self.tts:
            self._pending_speech.append(message)

        self._flush_speech()

    def _flush_speech(self):
        """Say queued alerts as soon as no conversation is running."""

        while self._pending_speech:

            if not self._lock.acquire(blocking=False):
                return                                  # in a conversation: try again next tick

            try:
                message = self._pending_speech.pop(0)

                self.speaking(message)

                try:
                    self.tts.speak(message)
                except Exception:  # noqa: BLE001
                    logger.exception("Could not speak alert.")

                self.idle()

            finally:
                self._lock.release()

    def _send_hud(self, payload: dict):
        """Show (or clear) the holographic panels."""

        if not self.ws:
            return

        if payload.get("kind") == "clear":
            self.ws.send({"hud": None})
            return

        hold = float(payload.get("hold", self.config.get("hud_hold_seconds", 10)))

        self.ws.send({"hud": {**payload, "hold": min(max(hold, 3.0), 60.0)}})

    def _on_level(self, rms: float):
        """Microphone loudness for the UI's listening animation."""

        if self._state != "listening" or not self.ws:
            return

        now = time.monotonic()

        if now - self._last_level < self.LEVEL_INTERVAL:
            return

        self._last_level = now

        self.ws.send_level(min(1.0, (rms * 12) ** 0.7))
