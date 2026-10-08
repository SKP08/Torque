from torque.ai.brain import TorqueBrain
from torque.audio.tts_service import TTSService
from torque.core.conversation_manager import ConversationManager
from torque.websocket.websocket_service import WebSocketService


class AssistantController:

    def __init__(self, manager):

        self.manager = manager

        self.ws = manager.get(WebSocketService)

        self.brain = TorqueBrain()
        self.tts = TTSService()

        self.conversation = ConversationManager()

    def activate(self):

        if self.conversation.active:
            return

        self.conversation.start()

        try:

            while self.conversation.active:

                self.listening()

                text = self.conversation.listen()

                if not text:
                    continue

                print(f"\nUser   : {text}")

                if self.conversation.should_stop(text):

                    self.speaking("Goodbye!")

                    self.tts.speak("Alright! See you later.")

                    break

                # Save user's message
                self.conversation.add_user_message(text)

                self.thinking()

                # Web search notification
                if self.brain.router.needs_web(text):

                    self.searching()

                    announcement = self.get_web_announcement(text)

                    self.tts.speak(announcement)

                # Process request
                response = self.brain.process(
                    self.conversation.get_history()
                )

                # Save assistant's response
                self.conversation.add_assistant_message(response)

                print(f"Torque : {response}\n")

                self.speaking(response)

                self.tts.speak(response)

        finally:

            self.idle()

            self.conversation.stop()

    def get_web_announcement(self, text):

        text = text.lower()

        if any(word in text for word in (
            "weather",
            "temperature",
            "forecast",
            "rain",
        )):
            return "Let me check the latest weather."

        if any(word in text for word in (
            "news",
            "headline",
            "breaking",
        )):
            return "I'll look up the latest news."

        if any(word in text for word in (
            "price",
            "buy",
            "best",
            "top",
            "under",
            "review",
            "compare",
            "laptop",
            "phone",
            "gpu",
            "cpu",
        )):
            return "Let me look up the latest prices and recommendations."

        if any(word in text for word in (
            "match",
            "score",
            "winner",
            "ipl",
            "fifa",
            "football",
            "cricket",
        )):
            return "Let me check the latest sports information."

        if any(word in text for word in (
            "python",
            "version",
            "release",
            "update",
            "driver",
        )):
            return "Let me check the latest information."

        return "I'll search the web for that."

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
            self.ws.send(
                {
                    "state": state,
                    "message": message,
                }
            )