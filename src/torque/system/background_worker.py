from concurrent.futures import ThreadPoolExecutor
from loguru import logger
import time


class BackgroundWorker:

    def __init__(self):

        self.executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="TorqueWorker",
        )

        logger.success("Background Worker ready.")

    def submit(
        self,
        job_name: str,
        func,
        *args,
        **kwargs,
    ):

        logger.debug(f"Queued job: {job_name}")

        return self.executor.submit(
            self._run_job,
            job_name,
            func,
            *args,
            **kwargs,
        )

    def _run_job(
        self,
        job_name,
        func,
        *args,
        **kwargs,
    ):

        start = time.perf_counter()

        try:

            result = func(*args, **kwargs)

            elapsed = time.perf_counter() - start

            logger.success(
                f"{job_name} finished in {elapsed:.2f}s"
            )

            return result

        except Exception:  # noqa: BLE001

            logger.exception(
                f"{job_name} failed."
            )

    def shutdown(self):

        self.executor.shutdown(wait=False)