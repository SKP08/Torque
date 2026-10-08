from dataclasses import dataclass
from datetime import datetime


@dataclass
class Memory:

    key: str

    value: str

    category: str

    created_at: datetime

    updated_at: datetime