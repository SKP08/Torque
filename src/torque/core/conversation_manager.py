from loguru import logger

from torque.conversation.conversation_policy import is_stop_phrase


class ConversationManager:
    """
    Owns the state of one spoken conversation: whether it is active, the
    message history, and the microphone.
    """

    MAX_HISTORY = 12

    def __init__(self, speech=None):

        if speech is None:
            from torque.audio.speech_service import SpeechService

            speech = SpeechService()

        self.speech = speech

        self.active = False

        self.history = []

    # ==========================================================
    # LIFECYCLE
    # ==========================================================

    def start(self):

        # Clear any cancel/stop left over from the previous conversation.
        self.speech.reset()

        self.active = True

        self.history.clear()

        logger.success("Conversation started.")

    def stop(self):

        self.active = False

        # Unblocks a microphone that is waiting for speech.
        self.speech.stop()

        logger.success("Conversation ended.")

    # ==========================================================
    # LISTENING
    # ==========================================================

    def listen(self, timeout=None, flush=True, preroll=None):
        """
        Returns the transcript, "" if speech was heard but nothing was
        recognised, or None if nobody spoke before the timeout / the
        conversation was cancelled.

        flush=True discards audio captured before this call (Torque's own
        voice); pass False when listening for the rest of a sentence.
        """

        if not self.active:
            return None

        if preroll:
            return self.speech.listen(timeout=timeout, flush=flush, preroll=preroll)

        return self.speech.listen(timeout=timeout, flush=flush)

    # ==========================================================
    # HISTORY
    # ==========================================================

    def add_user_message(self, text: str):
        self._add("user", text)

    def add_assistant_message(self, text: str):
        self._add("assistant", text)

    def _add(self, role: str, text: str):

        if not text:
            return

        self.history.append({"role": role, "content": text})

        self._trim_history()

    def get_history(self):
        return list(self.history)

    def clear_history(self):
        self.history.clear()

    def _trim_history(self):

        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]

        # Never start the context with an orphaned assistant reply.
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    # ==========================================================
    # STOP DETECTION
    # ==========================================================

    def should_stop(self, text: str) -> bool:
        return is_stop_phrase(text)
