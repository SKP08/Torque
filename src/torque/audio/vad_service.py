import torch
from loguru import logger
from silero_vad import VADIterator, load_silero_vad


class VADService:

    SAMPLE_RATE = 16000

    def __init__(self): 

        logger.info("Loading Silero VAD...")

        self.model = load_silero_vad()

        self.iterator = VADIterator(
            self.model,
            sampling_rate=self.SAMPLE_RATE,
        )

        logger.success("Silero VAD ready.")

    def reset(self):

        self.iterator.reset_states()

    def process(self, chunk):

        if not isinstance(
            chunk,
            torch.Tensor,
        ):

            chunk = torch.from_numpy(chunk)

        chunk = chunk.float()

        return self.iterator(chunk)