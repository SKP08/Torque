class SearchRouter:

    WEB_KEYWORDS = (
        # Time
        "today",
        "tomorrow",
        "yesterday",
        "latest",
        "current",
        "recent",
        "new",

        # News
        "news",
        "breaking",

        # Weather
        "weather",
        "temperature",
        "forecast",
        "rain",
        "humidity",

        # Sports
        "score",
        "match",
        "fixture",
        "winner",
        "who won",
        "standings",
        "points table",

        # Technology
        "version",
        "release",
        "update",
        "driver",
        "cve",
        "patch",

        # Shopping
        "best",
        "top",
        "recommend",
        "recommendation",
        "buy",
        "purchase",
        "price",
        "cost",
        "under",
        "budget",
        "compare",
        "comparison",
        "vs",
        "review",

        # Finance
        "stock",
        "share",
        "crypto",
        "bitcoin",
        "ethereum",
        "gold price",
        "silver price",

        # General
        "official",
        "live",
    )

    PRODUCT_WORDS = (
        "laptop",
        "phone",
        "mobile",
        "iphone",
        "android",
        "gpu",
        "graphics card",
        "cpu",
        "processor",
        "pc",
        "computer",
        "monitor",
        "keyboard",
        "mouse",
        "headphone",
        "earbuds",
        "camera",
        "tablet",
        "watch",
    )

    QUESTION_STARTERS = (
        "who",
        "when",
        "where",
    )

    def needs_web(self, text: str) -> bool:

        text = text.lower().strip()

        # Keyword triggers
        if any(keyword in text for keyword in self.WEB_KEYWORDS):
            return True

        # Product recommendation queries
        if any(product in text for product in self.PRODUCT_WORDS):

            recommendation_words = (
                "best",
                "top",
                "under",
                "buy",
                "recommend",
                "price",
                "cost",
                "review",
                "compare",
                "vs",
                "which",
                "good",
            )

            if any(word in text for word in recommendation_words):
                return True

        # Questions that usually need fresh information
        if text.startswith(self.QUESTION_STARTERS):

            freshness_words = (
                "current",
                "latest",
                "today",
                "yesterday",
                "winner",
                "president",
                "prime minister",
                "ceo",
            )

            if any(word in text for word in freshness_words):
                return True

        return False