import re

from torque.conversation.speech_analyzer import SpeechAnalyzer

# "bye", "goodbye for now", "okay thanks, bye bye", "that's all", ...
_STOP = re.compile(
    r"^(?:(?:ok|okay|alright)[\s,]+)?"
    r"(?:(?:thanks?|thank you)[\s,]+)?"
    r"(?:"
    r"bye(?:[\s-]bye)?|goodbye|see you(?: later| soon| tomorrow)?|"
    r"good ?night|that'?s all(?: for now)?|that will be all|"
    r"stop listening|go to sleep|go away|leave me alone|dismissed"
    r")"
    r"(?:\s+(?:for now|torque))?$"
)


def is_stop_phrase(text: str) -> bool:

    if not text:
        return False

    normalized = re.sub(r"\s+", " ", text.lower()).strip(" .,!?")

    return bool(_STOP.match(normalized))


class ConversationPolicy:
    """
    Interprets what the user said: is it empty, a throwaway
    acknowledgement, an unfinished sentence, or a real request?
    """

    def __init__(self):
        self.analyzer = SpeechAnalyzer()

    def analyze_input(self, text: str) -> dict:

        analysis = self.analyzer.analyze(text)

        effective_text = self.analyzer.extract_corrected_text(text)

        if not analysis["text"]:
            intent = "empty"
        elif analysis["short_acknowledgement"]:
            intent = "acknowledgement"
        elif analysis["appears_incomplete"]:
            intent = "incomplete"
        else:
            intent = "request"

        return {
            **analysis,
            "intent": intent,
            "should_process": intent == "request",
            "effective_text": effective_text,
        }

    def is_incomplete(self, text: str) -> bool:
        return self.analyzer.appears_incomplete(text)

    def is_acknowledgement(self, text: str) -> bool:
        return self.analyzer.is_short_acknowledgement(text)

    def is_stop_phrase(self, text: str) -> bool:
        return is_stop_phrase(text)
