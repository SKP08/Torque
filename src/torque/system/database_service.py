import sqlite3
from pathlib import Path

from loguru import logger

from torque.system.service import Service


class DatabaseService(Service):

    @property
    def name(self):
        return "Database Service"

    def initialize(self):

        database = Path("data/memory.db")

        if not database.exists():
            sqlite3.connect(database)
            logger.info("Database created.")
        else:
            logger.info("Database found.")