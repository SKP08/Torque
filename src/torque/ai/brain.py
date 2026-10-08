import re

from loguru import logger

from torque.ai.context_builder import ContextBuilder
from torque.ai.ollama_service import OllamaService
from torque.conversation.conversation_policy import ConversationPolicy
from torque.memory.memory_service import MemoryService
from torque.system.app_launcher import AppLauncher
from torque.system.background_worker import BackgroundWorker
from torque.system.system_router import SystemRouter
from torque.web.search_router import SearchRouter
from torque.web.web_service import WebService


class TorqueBrain:

    def __init__(self):

        logger.info(
            "Initializing Torque Brain..."
        )

        self.context = ContextBuilder()
        self.llm = OllamaService()
        self.memory = MemoryService()

        self.worker = BackgroundWorker()

        self.web = WebService()
        self.router = SearchRouter()

        self.system_router = SystemRouter()
        self.app_launcher = AppLauncher()

        # Conversation intelligence layer.
        self.conversation_policy = (
            ConversationPolicy()
        )

        logger.success(
            "Torque Brain ready."
        )

    # ==========================================================
    # COMMAND SPLITTING
    # ==========================================================

    def _split_system_commands(
        self,
        text: str,
    ) -> list[str]:
        """
        Split multiple system commands from a single request.

        Examples:

            "open chrome, open discord"
                ->
                [
                    "open chrome",
                    "open discord"
                ]

            "open chrome and then open discord"
                ->
                [
                    "open chrome",
                    "open discord"
                ]

            "open chrome"
                ->
                [
                    "open chrome"
                ]

        This is intentionally conservative.
        We only split when the second section clearly
        starts with another system command.
        """

        if not text:
            return []

        text = text.strip()

        # ------------------------------------------------------
        # First split on commas.
        # ------------------------------------------------------

        comma_parts = [
            part.strip()
            for part in re.split(
                r"\s*,\s*",
                text,
            )
            if part.strip()
        ]

        if len(comma_parts) > 1:

            commands = []

            current = comma_parts[0]

            for part in comma_parts[1:]:

                # Only create a new command if this part
                # actually begins with a known system command.
                if self._starts_with_system_command(
                    part
                ):

                    commands.append(
                        current
                    )

                    current = part

                else:

                    # Otherwise this is probably part of
                    # the previous command.
                    current = (
                        f"{current}, {part}"
                    )

            commands.append(
                current
            )

            if len(commands) > 1:

                return commands

        # ------------------------------------------------------
        # Handle "and then".
        # ------------------------------------------------------

        parts = re.split(
            r"\s+\band then\b\s+",
            text,
            flags=re.IGNORECASE,
        )

        if len(parts) > 1:

            commands = [
                part.strip()
                for part in parts
                if part.strip()
            ]

            if all(
                self._starts_with_system_command(
                    command
                )
                for command in commands
            ):

                return commands

        # ------------------------------------------------------
        # Handle "then".
        # ------------------------------------------------------

        parts = re.split(
            r"\s+\bthen\b\s+",
            text,
            flags=re.IGNORECASE,
        )

        if len(parts) > 1:

            commands = [
                part.strip()
                for part in parts
                if part.strip()
            ]

            if all(
                self._starts_with_system_command(
                    command
                )
                for command in commands
            ):

                return commands

        return [text]

    def _starts_with_system_command(
        self,
        text: str,
    ) -> bool:

        text = text.strip().lower()

        commands = (
            *SystemRouter.OPEN_COMMANDS,
            *SystemRouter.CLOSE_COMMANDS,
        )

        return any(
            text == command
            or text.startswith(
                command + " "
            )
            for command in commands
        )
    # ==========================================================
    # SYSTEM COMMAND PROCESSING
    # ==========================================================

    def _execute_system_command(
        self,
        system: dict,
    ) -> str | None:

        if not system:
            return None

        action = system.get("action")

        target = system.get(
            "target",
            "",
        )

        if target:
            target = target.strip()

        # ------------------------------------------------------
        # OPEN
        # ------------------------------------------------------

        if action == "open":

            if not target:
                return None

            logger.info(
                f"Processing system command: "
                f"'open {target}'"
            )

            success = self.app_launcher.launch(
                target
            )

            if success:

                return (
                    f"Opening {target}."
                )

            return (
                f"I couldn't find "
                f"{target} "
                f"on your computer."
            )

        # ------------------------------------------------------
        # CLOSE
        # ------------------------------------------------------

        if action == "close":

            if not target:
                return None

            logger.info(
                f"Processing system command: "
                f"'close {target}'"
            )

            # Close is not implemented yet.
            #
            # Do not pretend that it succeeded.
            return (
                f"Closing {target} "
                f"is not implemented yet."
            )

        return None

    def _process_system_commands(
        self,
        text: str,
    ) -> str | None:

        if not text:
            return None

        # ------------------------------------------------------
        # Ask SystemRouter to interpret the complete request.
        # ------------------------------------------------------

        system = self.system_router.route(
            text
        )

        if not system:

            logger.debug(
                f"Not a system command: "
                f"'{text}'"
            )

            return None

        action = system.get(
            "action"
        )

        # ------------------------------------------------------
        # SEQUENCE
        #
        # Example:
        #
        # "open chrome, open discord"
        #
        # SystemRouter returns:
        #
        # {
        #     "action": "sequence",
        #     "commands": [
        #         {
        #             "action": "open",
        #             "target": "chrome"
        #         },
        #         {
        #             "action": "open",
        #             "target": "discord"
        #         }
        #     ]
        # }
        # ------------------------------------------------------

        if action == "sequence":

            commands = system.get(
                "commands",
                [],
            )

            if not commands:

                logger.warning(
                    "SystemRouter returned an "
                    "empty command sequence."
                )

                return None

            logger.info(
                f"Processing system sequence "
                f"with {len(commands)} commands."
            )

            results = []

            for index, command in enumerate(
                commands,
                start=1,
            ):

                logger.info(
                    f"Executing command "
                    f"{index}/{len(commands)}: "
                    f"{command}"
                )

                result = (
                    self._execute_system_command(
                        command
                    )
                )

                if result:

                    results.append(
                        result
                    )

            if not results:

                return None

            return " ".join(
                results
            )

        # ------------------------------------------------------
        # SINGLE COMMAND
        # ------------------------------------------------------

        result = (
            self._execute_system_command(
                system
            )
        )

        return result

    # ==========================================================
    # MAIN BRAIN
    # ==========================================================

    def process(
        self,
        history: list,
    ) -> str:

        logger.info(
            "Brain processing request..."
        )

        last_user = next(
            (
                msg["content"]
                for msg in reversed(history)
                if msg["role"] == "user"
            ),
            "",
        )

        if not last_user:

            logger.warning(
                "Brain received no user input."
            )

            return "I didn't catch that."

        # ------------------------------------------------------
        # CONVERSATION ANALYSIS
        # ------------------------------------------------------

        policy = (
            self.conversation_policy.analyze_input(
                last_user
            )
        )

        effective_text = policy[
            "effective_text"
        ]

        logger.info(
            f"Conversation intent: "
            f"{policy['intent']}"
        )

        if effective_text != last_user:

            logger.info(
                "Corrected input: "
                f"'{last_user}' → "
                f"'{effective_text}'"
            )

        # ------------------------------------------------------
        # SYSTEM COMMANDS
        # ------------------------------------------------------

        system_response = (
            self._process_system_commands(
                effective_text
            )
        )

        if system_response:

            logger.info(
                "Using System Commands..."
            )

            return system_response

        # ------------------------------------------------------
        # WEB SEARCH
        # ------------------------------------------------------

        if self.router.needs_web(
            effective_text
        ):

            logger.info(
                "Using Web Search..."
            )

            result = self.web.search(
                effective_text
            )

            return result.answer

        # ------------------------------------------------------
        # LLM
        # ------------------------------------------------------

        messages = self.context.build(
            history
        )

        response = self.llm.chat(
            messages
        )

        # ------------------------------------------------------
        # MEMORY
        # ------------------------------------------------------

        if effective_text:

            self.worker.submit(
                "Memory Extraction",
                self.memory.extract,
                effective_text,
            )

        return response

    # ==========================================================
    # SHUTDOWN
    # ==========================================================

    def shutdown(self):

        self.worker.shutdown()


