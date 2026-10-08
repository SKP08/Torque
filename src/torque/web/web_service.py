import os

from dotenv import load_dotenv
from loguru import logger
from tavily import TavilyClient

from torque.web.internet_service import InternetService
from torque.web.search_result import SearchResult

load_dotenv()


class WebService:

    def __init__(self):

        self.api_key = os.getenv("TAVILY_API_KEY")

        if not self.api_key:
            raise RuntimeError(
                "TAVILY_API_KEY not found in .env"
            )

        self.client = TavilyClient(
            api_key=self.api_key
        )

        logger.success("Web Service ready.")

    def search(self, query: str) -> SearchResult:

        if not InternetService.connected():

            logger.warning("No internet connection.")

            return SearchResult(
                answer="I couldn't connect to the internet right now.",
                sources=[],
                success=False,
            )

        logger.info(f"Searching web: {query}")

        try:

            response = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_answer=True,
                include_raw_content=False,
            )

            answer = response.get("answer", "")

            results = response.get("results", [])

            if not answer:

                answer = "\n\n".join(
                    result.get("content", "")
                    for result in results
                )

            sources = [
                result.get("url")
                for result in results
                if result.get("url")
            ]

            logger.success("Web search completed.")

            return SearchResult(
                answer=answer,
                sources=sources,
                success=True,
            )

        except Exception:

            logger.exception("Web search failed.")

            return SearchResult(
                answer="Something went wrong while searching the web.",
                sources=[],
                success=False,
            )