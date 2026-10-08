from loguru import logger

from torque.audio.speech_service import SpeechService


class ConversationManager:

    MAX_HISTORY = 10

    # Phrases that explicitly mean the user wants to end
    # the conversation with Torque.
    STOP_PHRASES = {
        "bye",
        "goodbye",
        "see you",
        "thank you bye",
        "go away",
        "fuck off",
    }

    def __init__(self):

        self.speech = SpeechService()

        self.active = False

        self.history = []

    # ==========================================================
    # CONVERSATION LIFECYCLE
    # ==========================================================

    def start(self):

        # Reset any previous microphone state before
        # starting a fresh conversation.
        self.speech.reset()

        self.active = True

        self.history.clear()

        logger.success(
            "Conversation started."
        )

    def stop(self):

        self.active = False

        # Stop microphone recording immediately if active.
        self.speech.stop()

        logger.success(
            "Conversation ended."
        )

    # ==========================================================
    # LISTENING
    # ==========================================================

    def listen(self):

        if not self.active:

            logger.debug(
                "Listen requested while conversation is inactive."
            )

            return None

        return self.speech.listen()

    # ==========================================================
    # HISTORY
    # ==========================================================

    def add_user_message(self, text: str):

        if not text:
            return

        self.history.append(
            {
                "role": "user",
                "content": text,
            }
        )

        self._trim_history()

    def add_assistant_message(self, text: str):

        if not text:
            return

        self.history.append(
            {
                "role": "assistant",
                "content": text,
            }
        )

        self._trim_history()

    def get_history(self):

        return list(self.history)

    def clear_history(self):

        self.history.clear()

        logger.info(
            "Conversation history cleared."
        )

    def _trim_history(self):

        if len(self.history) > self.MAX_HISTORY:

            self.history = (
                self.history[-self.MAX_HISTORY:]
            )

    # ==========================================================
    # CONVERSATION STOP DETECTION
    # ==========================================================

    def should_stop(
        self,
        text: str,
    ) -> bool:

        if not text:

            return False

        normalized = (
            text.lower()
            .strip()
            .rstrip(".,!?")
        )

        # Only explicit conversational phrases should
        # terminate the conversation.
        return normalized in self.STOP_PHRASES