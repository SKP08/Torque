from loguru import logger

from torque.paths import DATA_DIR, MEMORY_DB
from torque.system.service import Service


class DatabaseService(Service):
    """
    Makes sure the data directory exists. The tables themselves are created
    by the component that owns them (see MemoryStore).
    """

    @property
    def name(self):
        return "Database Service"

    def initialize(self):

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        if MEMORY_DB.exists():
            logger.info("Database found.")
        else:
            logger.info("Database will be created on first use.")
