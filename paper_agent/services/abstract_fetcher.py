from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from paper_agent.config import get_settings


@dataclass(slots=True)
class PaperAbstractLookupResult:
    title: str
    abstract: str
    url: str | None = None
    venue: str | None = None
    year: int | None = None


class AbstractFetcher:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_abstract(self, url: str) -> str | None:
        normalized_url = self._normalize_url(url)
        headers = {"User-Agent": self.settings.paper_fetch_user_agent}

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.settings.http_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(normalized_url)
            response.raise_for_status()

        return self._extract_abstract(response.text)

    async def lookup_abstract_by_title(
        self,
        title: str,
        venue: str | None = None,
        year: int | None = None,
    ) -> PaperAbstractLookupResult | None:
        headers = {"User-Agent": self.settings.paper_fetch_user_agent}
        params = {
            "search": title,
            "per-page": 5,
            "select": "display_name,abstract_inverted_index,primary_location,publication_year,primary_topic,host_venue",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.settings.http_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get("https://api.openalex.org/works", params=params)
            response.raise_for_status()

        payload = response.json()
        results = payload.get("results", [])
        normalized_title = self._normalize_title(title)
        best_match: PaperAbstractLookupResult | None = None
        best_score = 0.0

        for item in results:
            candidate_title = self._clean_text(item.get("display_name", "") or "")
            abstract = self._extract_inverted_index_text(item.get("abstract_inverted_index"))
            if not candidate_title or not abstract:
                continue

            score = self._title_similarity(normalized_title, self._normalize_title(candidate_title))
            candidate_year = item.get("publication_year")
            candidate_venue = self._extract_openalex_venue(item)

            if year and candidate_year and candidate_year != year:
                score -= 0.05
            if venue and candidate_venue and venue.lower() not in candidate_venue.lower():
                score -= 0.05
            if score > best_score:
                primary_location = item.get("primary_location") or {}
                best_score = score
                best_match = PaperAbstractLookupResult(
                    title=candidate_title,
                    abstract=abstract,
                    url=primary_location.get("landing_page_url") or primary_location.get("pdf_url"),
                    venue=candidate_venue,
                    year=candidate_year,
                )

        if best_score < 0.72:
            return None
        return best_match

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        if "arxiv.org" in parsed.netloc and parsed.path.startswith("/pdf/"):
            paper_id = parsed.path.removeprefix("/pdf/").removesuffix(".pdf")
            return f"{parsed.scheme}://{parsed.netloc}/abs/{paper_id}"
        return url

    def _extract_abstract(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")

        selectors = [
            ('meta[name="citation_abstract"]', "content"),
            ('meta[name="dc.description"]', "content"),
            ('meta[property="og:description"]', "content"),
            ('meta[name="twitter:description"]', "content"),
            ('meta[name="description"]', "content"),
        ]
        for selector, attribute in selectors:
            element = soup.select_one(selector)
            if element and element.get(attribute):
                return self._clean_text(element[attribute])

        abstract_block = soup.select_one("blockquote.abstract")
        if abstract_block:
            return self._clean_text(abstract_block.get_text(" ", strip=True).removeprefix("Abstract:"))

        for heading_text in ("abstract", "summary"):
            heading = soup.find(lambda tag: tag.name in {"h1", "h2", "h3", "strong"} and heading_text in tag.get_text(" ", strip=True).lower())
            if not heading:
                continue
            sibling = heading.find_next(["p", "div"])
            if sibling:
                return self._clean_text(sibling.get_text(" ", strip=True))

        return None

    def _clean_text(self, value: str) -> str | None:
        cleaned = " ".join(value.split())
        return cleaned or None

    def _extract_inverted_index_text(self, value: dict[str, list[int]] | None) -> str | None:
        if not value:
            return None
        positioned_words: list[tuple[int, str]] = []
        for word, positions in value.items():
            for position in positions:
                positioned_words.append((position, word))
        if not positioned_words:
            return None
        ordered_words = [word for _, word in sorted(positioned_words, key=lambda item: item[0])]
        return self._clean_text(" ".join(ordered_words))

    def _normalize_title(self, value: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
        return " ".join(cleaned.split())

    def _title_similarity(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        return (2 * overlap) / (len(left_tokens) + len(right_tokens))

    def _extract_openalex_venue(self, item: dict) -> str | None:
        primary_topic = item.get("primary_topic") or {}
        host_venue = item.get("host_venue") or {}
        if host_venue.get("display_name"):
            return self._clean_text(host_venue["display_name"])
        if primary_topic.get("display_name"):
            return self._clean_text(primary_topic["display_name"])
        return None
