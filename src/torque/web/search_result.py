from dataclasses import dataclass


@dataclass
class SearchResult:

    answer: str

    sources: list[str]

    success: bool = True