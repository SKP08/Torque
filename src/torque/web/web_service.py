import os

from dotenv import load_dotenv
from loguru import logger

from torque.paths import PROJECT_ROOT
from torque.system.config_service import load_config
from torque.web.search_result import SearchResult

load_dotenv(PROJECT_ROOT / ".env")

SEARCH_TIMEOUT = 10


def _is_network_error(error: Exception) -> bool:

    try:
        import requests

        if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True

    except ImportError:
        pass

    return isinstance(error, (ConnectionError, TimeoutError, OSError))


class WebService:
    """
    Web search through Tavily. Missing configuration disables search
    instead of stopping Torque from starting.

    Uses Tavily's "basic" depth by default: about twice as fast as
    "advanced" and plenty for spoken answers.
    """

    def __init__(self, client=None, depth=None):

        self.api_key = os.getenv("TAVILY_API_KEY")
        self.client = client
        self.depth = depth or load_config()["web_search_depth"]

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

        logger.info("Searching the web...")

        try:
            response = self.client.search(
                query=query,
                search_depth=self.depth,
                max_results=3,
                include_answer=True,
                include_raw_content=False,
                timeout=SEARCH_TIMEOUT,
            )

            answer = response.get("answer", "")

            results = response.get("results", [])

            if not answer:
                answer = "\n\n".join(result.get("content", "") for result in results[:2])

            sources = [r.get("url") for r in results if r.get("url")]

            if not answer:
                return SearchResult(
                    answer="I searched, but didn't find a clear answer.",
                    sources=sources,
                    success=False,
                )

            return SearchResult(answer=answer, sources=sources, success=True)

        except Exception as error:  # noqa: BLE001

            if _is_network_error(error):
                logger.warning(f"Web search could not connect: {error}")

                return SearchResult(
                    answer="I couldn't connect to the internet right now.",
                    sources=[],
                    success=False,
                )

            logger.exception("Web search failed.")

            return SearchResult(
                answer="Something went wrong while searching the web.",
                sources=[],
                success=False,
            )
