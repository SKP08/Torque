import socket


class InternetService:

    @staticmethod
    def connected() -> bool:

        try:

            socket.create_connection(
                ("8.8.8.8", 53),
                timeout=2,
            )

            return True

        except OSError:

            return False