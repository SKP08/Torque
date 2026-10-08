from enum import Enum


class ConversationState(Enum):

    IDLE = "idle"

    LISTENING = "listening"

    MAYBE_FINISHED = "maybe_finished"

    CONTINUING = "continuing"

    THINKING = "thinking"

    SPEAKING = "speaking"

    INTERRUPTED = "interrupted"

    EXECUTING = "executing"

    WAITING = "waiting"