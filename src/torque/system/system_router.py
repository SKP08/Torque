import re


class SystemRouter:

    OPEN_COMMANDS = (
        "open",
        "launch",
        "start",
        "run",
    )

    CLOSE_COMMANDS = (
        "close",
        "exit",
        "quit",
    )

    # Words/phrases that can separate commands.
    COMMAND_SEPARATORS = (
        "and then",
        "then",
        "and",
    )

    # Words that can appear when the user corrects themselves.
    CORRECTION_MARKERS = (
        "actually",
        "wait",
        "sorry",
        "no",
        "rather",
        "instead",
        "correction",
    )

    def _clean(self, text: str) -> str:

        if not text:
            return ""

        text = text.lower().strip()

        # Normalize punctuation into spaces.
        text = re.sub(
            r"[.!?;:]",
            " ",
            text,
        )

        # Normalize commas.
        text = re.sub(
            r"\s*,\s*",
            ", ",
            text,
        )

        # Collapse whitespace.
        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    def _clean_target(self, target: str) -> str:

        target = target.strip()

        # Remove punctuation around target.
        target = re.sub(
            r"^[,\s]+|[,\s]+$",
            "",
            target,
        )

        # Remove conversational endings.
        trailing_phrases = (
            "thank you",
            "thanks",
            "yeah",
            "okay",
            "ok",
            "right",
        )

        changed = True

        while changed:

            changed = False

            for phrase in trailing_phrases:

                pattern = (
                    rf"\s+{re.escape(phrase)}$"
                )

                cleaned = re.sub(
                    pattern,
                    "",
                    target,
                    flags=re.IGNORECASE,
                ).strip()

                if cleaned != target:

                    target = cleaned
                    changed = True

        return target

    def _match_command(self, text: str):

        text = text.strip()

        # ---------------- OPEN ----------------

        for command in self.OPEN_COMMANDS:

            if text == command:

                return {
                    "action": "open",
                    "target": "",
                }

            prefix = command + " "

            if text.startswith(prefix):

                target = text[
                    len(command):
                ].strip()

                return {
                    "action": "open",
                    "target": self._clean_target(
                        target
                    ),
                }

        # ---------------- CLOSE ----------------

        for command in self.CLOSE_COMMANDS:

            if text == command:

                return {
                    "action": "close",
                    "target": "",
                }

            prefix = command + " "

            if text.startswith(prefix):

                target = text[
                    len(command):
                ].strip()

                return {
                    "action": "close",
                    "target": self._clean_target(
                        target
                    ),
                }

        return None

    def _remove_correction_prefix(
        self,
        text: str,
    ) -> str:
        """
        Handles cases such as:

            open edge actually open chrome
            open edge wait open chrome
            open edge sorry open chrome
            open edge no sorry open chrome

        The final command should win.
        """

        text = text.strip()

        # Look for the LAST correction marker.
        matches = []

        for marker in self.CORRECTION_MARKERS:

            pattern = rf"\b{re.escape(marker)}\b"

            for match in re.finditer(
                pattern,
                text,
            ):

                matches.append(
                    (
                        match.start(),
                        match.end(),
                    )
                )

        if not matches:
            return text

        matches.sort(
            key=lambda item: item[0]
        )

        _, end = matches[-1]

        remainder = text[end:].strip()

        # Remove another correction marker if the
        # sequence was "no sorry open ..."
        for marker in self.CORRECTION_MARKERS:

            prefix = marker + " "

            if remainder.startswith(prefix):

                remainder = remainder[
                    len(marker):
                ].strip()

        return remainder

    def _split_commands(
        self,
        text: str,
    ) -> list[str]:
        """
        Split a natural-language request into individual
        system commands.

        Examples:

            open chrome, open discord

            -> [
                "open chrome",
                "open discord"
            ]

            open chrome and then open discord

            -> [
                "open chrome",
                "open discord"
            ]

            open edge open file explorer

            -> [
                "open edge",
                "open file explorer"
            ]
        """

        text = text.strip()

        if not text:
            return []

        # --------------------------------------------------
        # First split explicitly on commas.
        # --------------------------------------------------

        comma_parts = [
            part.strip()
            for part in text.split(",")
            if part.strip()
        ]

        parts = []

        for part in comma_parts:

            # --------------------------------------------------
            # Split "and then", "then", and "and" only when
            # another command follows.
            # --------------------------------------------------

            pattern = (
                r"\s+(?:and\s+then|then|and)"
                r"\s+(?=(?:open|launch|start|run|close|exit|quit)\b)"
            )

            subparts = re.split(
                pattern,
                part,
                flags=re.IGNORECASE,
            )

            parts.extend(
                p.strip()
                for p in subparts
                if p.strip()
            )

        # --------------------------------------------------
        # Whisper sometimes removes punctuation completely:
        #
        # "open microsoft edge open file explorer"
        #
        # Detect another command appearing in the middle.
        # --------------------------------------------------

        final_parts = []

        command_pattern = re.compile(
            r"\b(?:open|launch|start|run|close|exit|quit)\b",
            re.IGNORECASE,
        )

        for part in parts:

            matches = list(
                command_pattern.finditer(part)
            )

            if len(matches) <= 1:

                final_parts.append(part)
                continue

            for index, match in enumerate(matches):

                start = match.start()

                if index + 1 < len(matches):

                    end = matches[
                        index + 1
                    ].start()

                    command_text = part[
                        start:end
                    ].strip()

                else:

                    command_text = part[
                        start:
                    ].strip()

                if command_text:
                    final_parts.append(
                        command_text
                    )

        return final_parts

    def route(self, text: str):

        text = self._clean(text)

        if not text:
            return None

        # --------------------------------------------------
        # CORRECTION HANDLING
        #
        # If the user says:
        #
        # "open edge no sorry open file explorer"
        #
        # the final request should win.
        # --------------------------------------------------

        correction_pattern = re.compile(
            r"\b(?:actually|wait|sorry|"
            r"no\s+sorry|rather|instead|correction)\b",
            re.IGNORECASE,
        )

        if correction_pattern.search(text):

            # Don't blindly throw away everything before
            # the correction if this is a normal command
            # containing "actually" etc.
            #
            # Find the last command following a correction.
            matches = list(
                correction_pattern.finditer(text)
            )

            if matches:

                last_marker = matches[-1]

                remainder = text[
                    last_marker.end():
                ].strip()

                # Handle:
                #
                # "no sorry open file explorer"
                #
                remainder = re.sub(
                    r"^(?:no\s+)?sorry\s+",
                    "",
                    remainder,
                    flags=re.IGNORECASE,
                ).strip()

                # Only replace the request if a valid command
                # actually follows the correction.
                if re.match(
                    r"^(?:open|launch|start|run|close|exit|quit)\b",
                    remainder,
                    flags=re.IGNORECASE,
                ):

                    text = remainder

        # --------------------------------------------------
        # Split into individual commands.
        # --------------------------------------------------

        command_texts = self._split_commands(
            text
        )

        commands = []

        for command_text in command_texts:

            result = self._match_command(
                command_text
            )

            if result and result["target"]:

                commands.append(result)

        # --------------------------------------------------
        # Nothing found.
        # --------------------------------------------------

        if not commands:
            return None

        # --------------------------------------------------
        # Single command.
        #
        # Keep the old API compatible.
        # --------------------------------------------------

        if len(commands) == 1:

            return commands[0]

        # --------------------------------------------------
        # Multiple commands.
        # --------------------------------------------------

        return {
            "action": "sequence",
            "commands": commands,
        }