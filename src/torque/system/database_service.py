import sqlite3
from pathlib import Path

from loguru import logger


class DatabaseService:

    def initialize(self):

        database = Path("data/memory.db")

        if not database.exists():

            sqlite3.connect(database)

            logger.info("Database created.")

        else:

            logger.info("Database found.")