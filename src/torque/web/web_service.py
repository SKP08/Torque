import os

from dotenv import load_dotenv
from loguru import logger

from torque.paths import PROJECT_ROOT
from torque.web.internet_service import InternetService
from torque.web.search_result import SearchResult

load_dotenv(PROJECT_ROOT / ".env")


class WebService:
    """
    Web search through Tavily. Missing configuration disables search
    instead of stopping Torque from starting.
    """

    def __init__(self, client=None):

        self.api_key = os.getenv("TAVILY_API_KEY")
        self.client = client

        if self.client is None and self.api_key:
            from tavily import TavilyClient

            self.client = TavilyClient(api_key=self.api_key)

        if self.client is None:
            logger.warning(
                "TAVILY_API_KEY not set; web search is disabled. "
                "Add it to .env to enable it."
            )
        else:
            logger.success("Web Service ready.")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def search(self, query: str) -> SearchResult:

        if not self.enabled:
            return SearchResult(
                answer="Web search isn't set up yet. Add your Tavily key to the .env file.",
                sources=[],
                success=False,
            )

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
                    result.get("content", "") for result in results[:2]
                )

            sources = [r.get("url") for r in results if r.get("url")]

            if not answer:
                return SearchResult(
                    answer="I searched, but didn't find a clear answer.",
                    sources=sources,
                    success=False,
                )

            logger.success("Web search completed.")

            return SearchResult(answer=answer, sources=sources, success=True)

        except Exception:  # noqa: BLE001
            logger.exception("Web search failed.")

            return SearchResult(
                answer="Something went wrong while searching the web.",
                sources=[],
                success=False,
            )
