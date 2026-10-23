import re


def _words(*words: str) -> re.Pattern:
    """Whole-word / whole-phrase matcher (no substring false positives)."""

    return re.compile(
        r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b",
        re.IGNORECASE,
    )


class SearchRouter:
    """
    Decides whether a request needs fresh information from the web.

    Rules are deliberately word-boundary based. Ambiguous words
    ("best", "update", "today") only count when combined with context.
    """

    # Things that are almost always about live information.
    STRONG = _words(
        "news", "headlines", "breaking news",
        "weather", "temperature", "forecast", "humidity",
        "rain", "raining", "snow", "snowing",
        "score", "scores", "standings", "fixtures", "points table", "who won",
        "stocks", "stock market", "crypto", "bitcoin", "ethereum",
        "exchange rate", "gold price", "silver price", "price of",
        "going on in the world", "happening in the world", "happening right now",
    )

    CVE = re.compile(r"\bcve(?:-\d{4}-\d+)?\b", re.IGNORECASE)

    STOCK_CONTEXT = re.compile(
        r"\bstock\b.*\b(?:price|market|ticker|shares|trading|doing|today|at)\b"
        r"|\b(?:price|market|ticker|shares|trading|doing|today)\b.*\bstock\b",
        re.IGNORECASE,
    )

    MARKET_CONTEXT = re.compile(
        r"\bmarkets?\b.*\b(?:doing|today|open|closed|up|down|crash)\b",
        re.IGNORECASE,
    )

    # Freshness words only matter in a question or request for information.
    FRESHNESS = _words(
        "latest", "newest", "recent", "recently",
        "today", "tomorrow", "tonight", "yesterday", "right now",
        "this week", "this month", "this year",
    )

    QUESTION_START = re.compile(
        r"^(?:what|what's|whats|who|who's|when|where|which|how|is|are|did|does|"
        r"will|tell me|give me|any|has|have)\b",
        re.IGNORECASE,
    )

    SHOPPING = _words(
        "best", "top", "recommend", "recommendation", "recommendations",
        "buy", "purchase", "price", "prices", "cost", "cheapest",
        "review", "reviews", "compare", "comparison", "vs", "versus",
        "budget", "which",
    )

    UNDER_BUDGET = re.compile(r"\bunder\s+\$?\d", re.IGNORECASE)

    PRODUCTS = _words(
        "laptop", "laptops", "phone", "phones", "iphone", "android",
        "gpu", "graphics card", "cpu", "processor", "monitor", "keyboard",
        "mouse", "headphones", "earbuds", "camera", "tablet", "smartwatch",
    )

    TECH_THING = _words("version", "release", "update", "driver", "patch")
    TECH_FRESH = _words("latest", "newest", "current", "new", "download")

    OFFICE = _words(
        "president", "prime minister", "ceo", "chancellor", "governor", "mayor",
    )
    WH_START = re.compile(r"^(?:who|when|where|what)\b", re.IGNORECASE)

    def needs_web(self, text: str) -> bool:

        text = (text or "").strip()

        if not text:
            return False

        if (
            self.STRONG.search(text)
            or self.CVE.search(text)
            or self.STOCK_CONTEXT.search(text)
            or self.MARKET_CONTEXT.search(text)
        ):
            return True

        # "latest python version", "current graphics driver"
        if self.TECH_THING.search(text) and self.TECH_FRESH.search(text):
            return True

        # "best laptop under 1000", "iphone vs pixel"
        if self.PRODUCTS.search(text) and (
            self.SHOPPING.search(text) or self.UNDER_BUDGET.search(text)
        ):
            return True

        # "who is the current prime minister of canada"
        if self.WH_START.search(text) and self.OFFICE.search(text):
            return True

        # "what's the latest on the spacex launch"
        if self.FRESHNESS.search(text) and self.QUESTION_START.search(text):
            return True

        return False

    # ----------------------------------------------------------

    ANNOUNCEMENTS = (
        (("weather", "temperature", "forecast", "rain", "raining", "snow", "humidity"),
         "Let me check the latest weather."),
        (("news", "headlines", "breaking news", "going on in the world",
          "happening in the world"),
         "I'll look up the latest news."),
        (("score", "scores", "standings", "fixtures", "points table", "who won"),
         "Let me check the latest sports information."),
        (("stocks", "stock", "stock market", "market", "markets", "crypto",
          "bitcoin", "ethereum", "exchange rate", "gold price", "silver price"),
         "Let me check the latest market information."),
        (("price", "prices", "buy", "best", "top", "review", "reviews", "compare",
          "cheapest", "vs", "versus", "under"),
         "Let me look up the latest prices and recommendations."),
    )

    def announcement(self, text: str) -> str:
        """Short line Torque says before searching."""

        for words, line in self.ANNOUNCEMENTS:
            if _words(*words).search(text or ""):
                return line

        return "I'll search the web for that."
