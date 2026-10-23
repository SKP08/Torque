from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

from torque.hud.entities import extract_entities

MAX_PANELS = 3
DEADLINE = 6.0            # seconds to wait for Wikipedia in total


class InfoService:
    """Builds the "info" HUD payload for a question and its spoken answer."""

    def __init__(self, wiki):

        self.wiki = wiki

    def prefetch(self, question: str):
        """Warm the cache for the question's subjects while the answer is generated."""

        for name in extract_entities(question, "")[:2]:
            self._safe_summary(name)

    def _safe_summary(self, name):

        try:
            return self.wiki.summary(name)
        except Exception:  # noqa: BLE001
            logger.debug("Wikipedia summary failed.", exc_info=True)
            return None

    def build(self, question: str, answer: str):
        """{"kind": "info", ...} or None when there is nothing worth showing."""

        names = extract_entities(question, answer, limit=MAX_PANELS)

        if not names:
            return None

        cards = {}

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="TorqueWiki") as pool:

            futures = {pool.submit(self._safe_summary, n): n for n in names}

            try:
                for future in as_completed(futures, timeout=DEADLINE):
                    cards[futures[future]] = future.result()
            except TimeoutError:
                logger.debug("Some panel lookups timed out.")

        panels, titles = [], set()

        for name in names:                                  # keep the priority order

            card = cards.get(name)

            if not card or card["title"].lower() in titles:
                continue

            titles.add(card["title"].lower())
            panels.append(card)

            if len(panels) == MAX_PANELS:
                break

        if not panels:
            return None

        geo = next(
            ({"lat": p["lat"], "lon": p["lon"], "label": p["title"]} for p in panels if p.get("lat") is not None),
            None,
        )

        return {
            "kind": "info",
            "title": panels[0]["title"],
            "panels": [
                {k: p.get(k) for k in ("title", "description", "text", "image", "image_remote", "url")}
                for p in panels
            ],
            "geo": geo,
        }
