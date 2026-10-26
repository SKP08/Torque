import queue
import threading

FILLERS = ("One moment.", "Let me think.", "Give me a second.", "Working on it.")

_DONE = object()


class FillerGate:
    """
    Wraps a sentence generator: if the first sentence takes longer than
    `after` seconds, a short filler is yielded so the silence doesn't feel dead.
    Only the *first* wait counts; once speech is flowing nothing is inserted.
    Closing the wrapper (the user cut Torque off) stops the producer too.
    """

    def __init__(self, after=1.5, fillers=FILLERS):
        self.after = after
        self.fillers = fillers
        self._count = 0

    def _filler(self):
        text = self.fillers[self._count % len(self.fillers)]
        self._count += 1

        return text

    def wrap(self, generator):
        if not self.after or self.after <= 0:
            yield from generator
            return

        items = queue.Queue()
        stop = threading.Event()

        def produce():
            try:
                for item in generator:
                    if stop.is_set():
                        break

                    items.put(item)

            except BaseException as error:  # noqa: BLE001 - re-raised in the consumer
                items.put(error)

            finally:
                try:
                    close = getattr(generator, "close", None)

                    if close:
                        close()
                finally:
                    items.put(_DONE)         # the consumer must never be left waiting

        threading.Thread(target=produce, name="TorqueReply", daemon=True).start()

        waited = False

        try:
            while True:
                try:
                    item = items.get(timeout=None if waited else self.after)
                except queue.Empty:
                    waited = True
                    yield self._filler()
                    continue

                waited = True

                if item is _DONE:
                    return

                if isinstance(item, BaseException):
                    raise item

                yield item

        finally:
            stop.set()
