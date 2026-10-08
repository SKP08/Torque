from loguru import logger

from torque.conversation.conversation_state import ConversationState
from torque.conversation.speech_analyzer import SpeechAnalyzer


class ConversationPolicy:

    def __init__(self):

        self.analyzer = SpeechAnalyzer()

        self.state = ConversationState.IDLE

    def set_state(self, state: ConversationState):

        self.state = state

        logger.debug(
            f"Conversation state → {state.value}"
        )

    def analyze_input(self, text: str) -> dict:

        analysis = self.analyzer.analyze(text)

        # Extract the final intended request when the user
        # corrects themselves.
        corrected_text = (
            self.analyzer.extract_corrected_text(text)
        )

        decision = self._decide(analysis)

        result = {
            **analysis,
            **decision,
            "corrected_text": corrected_text,
            "effective_text": self._get_effective_text(
                analysis,
                corrected_text,
            ),
            "state": self.state.value,
        }

        logger.debug(
            f"Conversation policy: {result}"
        )

        return result

    def _get_effective_text(
        self,
        analysis: dict,
        corrected_text: str,
    ) -> str:

        original_text = analysis["text"]

        if (
            analysis["has_correction"]
            and corrected_text
            and corrected_text != original_text
        ):

            logger.info(
                f"Using corrected request: "
                f"'{original_text}' → '{corrected_text}'"
            )

            return corrected_text

        return original_text

    def _decide(self, analysis: dict) -> dict:

        if not analysis["text"]:

            return {
                "intent": "empty",
                "should_process": False,
                "should_continue": False,
                "is_correction": False,
                "is_acknowledgement": False,
            }

        # Very short responses such as:
        # "yeah", "okay", "right"
        if analysis["short_acknowledgement"]:

            return {
                "intent": "acknowledgement",
                "should_process": False,
                "should_continue": False,
                "is_correction": False,
                "is_acknowledgement": True,
            }

        # An incomplete sentence should remain open.
        if analysis["appears_incomplete"]:

            return {
                "intent": "incomplete",
                "should_process": False,
                "should_continue": True,
                "is_correction": analysis["has_correction"],
                "is_acknowledgement": False,
            }

        # A correction is still a complete request.
        #
        # Example:
        #
        # "Open Chrome... actually wait, open Edge."
        #
        # The final corrected request is stored in
        # "effective_text".
        if analysis["has_correction"]:

            return {
                "intent": "correction",
                "should_process": True,
                "should_continue": False,
                "is_correction": True,
                "is_acknowledgement": False,
            }

        # Fillers by themselves do NOT mean the user is unfinished.
        #
        # Example:
        #
        # "Yeah, umm, open Chrome."
        #
        # This is still a complete request.
        if analysis["has_filler"]:

            return {
                "intent": "request_with_filler",
                "should_process": True,
                "should_continue": False,
                "is_correction": False,
                "is_acknowledgement": False,
            }

        # Normal complete request.
        return {
            "intent": "request",
            "should_process": True,
            "should_continue": False,
            "is_correction": False,
            "is_acknowledgement": False,
        }

    def should_continue_listening(
        self,
        text: str,
    ) -> bool:

        analysis = self.analyzer.analyze(text)

        # Only an actually incomplete sentence should force
        # another listening cycle.
        return analysis["appears_incomplete"]

    def is_correction(
        self,
        text: str,
    ) -> bool:

        return self.analyzer.contains_correction(
            text
        )

    def is_acknowledgement(
        self,
        text: str,
    ) -> bool:

        return self.analyzer.is_short_acknowledgement(
            text
        )

    def mark_listening(self):

        self.set_state(
            ConversationState.LISTENING
        )

    def mark_thinking(self):

        self.set_state(
            ConversationState.THINKING
        )

    def mark_speaking(self):

        self.set_state(
            ConversationState.SPEAKING
        )

    def mark_interrupted(self):

        self.set_state(
            ConversationState.INTERRUPTED
        )

    def mark_executing(self):

        self.set_state(
            ConversationState.EXECUTING
        )

    def mark_idle(self):

        self.set_state(
            ConversationState.IDLE
        )