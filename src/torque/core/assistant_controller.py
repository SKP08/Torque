import threading

from loguru import logger

from torque.system.config_service import load_config
from torque.websocket.websocket_service import WebSocketService


class AssistantController:
    """
    Runs the voice conversation loop:

        listen -> understand -> (act | search | chat) -> speak -> repeat

    The conversation ends on a goodbye, on silence, or when cancelled
    (hotkey pressed again, or {"type": "cancel"} from the UI).
    """

    MAX_EMPTY_TURNS = 3
    MAX_CONTINUATIONS = 2
    CONTINUATION_TIMEOUT = 4.0

    def __init__(self, manager, brain=None, tts=None, conversation=None):

        self.manager = manager
        self.config = load_config()

        self.ws = manager.get(WebSocketService)

        if brain is None:
            from torque.ai.brain import TorqueBrain

            brain = TorqueBrain()

        if tts is None and self.config["voice_enabled"]:
            from torque.audio.tts_service import TTSService

            tts = TTSService()

        if conversation is None:
            from torque.core.conversation_manager import ConversationManager

            conversation = ConversationManager()

        self.brain = brain
        self.tts = tts
        self.conversation = conversation

        self._lock = threading.Lock()
        self._cancelled = threading.Event()

        if self.ws:
            self.ws.set_message_handler(self.handle_message)

        self.idle()

    # ==========================================================
    # ENTRY POINTS
    # ==========================================================

    def toggle(self):
        """Hotkey: start a conversation, or cancel the running one."""

        if self.conversation.active:
            self.cancel()
        else:
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

            self.thinking()

            self._respond()

        finally:
            self.idle()

            self._lock.release()

    def activate(self):

        if not self._lock.acquire(blocking=False):
            return

        self._cancelled.clear()

        try:
            self._conversation_loop()

        finally:
            self.idle()

            self.conversation.stop()

            self._lock.release()

    def shutdown(self):

        self.cancel()

        self.brain.shutdown()

    # ==========================================================
    # CONVERSATION LOOP
    # ==========================================================

    def _conversation_loop(self):

        self.conversation.start()

        timeout = self.config["listen_timeout"]

        empty_turns = 0

        while self.conversation.active:

            self.listening()

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

            empty_turns = 0

            text = self._complete_sentence(text)

            logger.info(f"User: {text}")

            if self.conversation.should_stop(text):

                self.speaking("Alright, see you later.")

                self._speak("Alright, see you later.")

                break

            if self.brain.conversation_policy.is_acknowledgement(text):
                continue

            self.conversation.add_user_message(text)

            self.thinking()

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

            more = self.conversation.listen(timeout=self.CONTINUATION_TIMEOUT)

            if not more:
                break

            text = f"{text} {more}"

        return text

    def _respond(self):

        try:
            response = self.brain.process(
                self.conversation.get_history(),
                on_status=self._on_brain_status,
            )

        except Exception:  # noqa: BLE001
            logger.exception("Brain failed.")

            response = "Something went wrong on my side."

        if not response or self._cancelled.is_set():
            return

        self.conversation.add_assistant_message(response)

        logger.info(f"Torque: {response}")

        self.speaking(response)

        self._speak(response)

    def _on_brain_status(self, state: str, message: str):

        self._send(state, message)

        if state == "searching":
            self._speak(message)

    def _speak(self, text: str):

        if not self.tts or self._cancelled.is_set():
            return

        try:
            self.tts.speak(text)

        except Exception:  # noqa: BLE001
            logger.exception("Text-to-speech failed.")

    # ==========================================================
    # UI STATE
    # ==========================================================

    def listening(self):
        self._send("listening", "Listening...")

    def thinking(self):
        self._send("thinking", "Thinking...")

    def searching(self):
        self._send("searching", "Searching the web...")

    def speaking(self, text):
        self._send("speaking", text)

    def idle(self):
        self._send("idle", "")

    def _send(self, state, message):

        if self.ws:
            self.ws.send({"state": state, "message": message})
