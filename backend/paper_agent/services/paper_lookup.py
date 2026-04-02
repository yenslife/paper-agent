from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from paper_agent.config import get_settings
from paper_agent.services.abstract_fetcher import AbstractFetcher


@dataclass(slots=True)
class PaperLookupResult:
    provider: str
    confidence: float
    title: str | None = None
    abstract: str | None = None
    url: str | None = None
    source_page_url: str | None = None
    pdf_url: str | None = None
    preprint_pdf_url: str | None = None
    slide_url: str | None = None
    video_url: str | None = None
    venue: str | None = None
    year: int | None = None
    doi: str | None = None
    external_ids: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PaperLookupService:
    def __init__(self, abstract_fetcher: AbstractFetcher | None = None) -> None:
        self.settings = get_settings()
        self.abstract_fetcher = abstract_fetcher or AbstractFetcher()

    async def lookup_paper(
        self,
        title: str,
        paper_url: str | None = None,
        source_page_url: str | None = None,
        venue: str | None = None,
        year: int | None = None,
    ) -> PaperLookupResult | None:
        normalized_title = self._normalize_title(title)
        page_lookup = await self._lookup_from_known_page(
            title=title,
            paper_url=paper_url,
            source_page_url=source_page_url,
            venue=venue,
            year=year,
        )

        semantic_lookup = await self._lookup_via_semantic_scholar(
            title=title,
            venue=venue,
            year=year,
        )
        best_external = semantic_lookup
        if best_external is None:
            best_external = await self._lookup_via_openalex(
                title=title,
                venue=venue,
                year=year,
            )

        if page_lookup and best_external:
            return self._merge_lookup_results(page_lookup, best_external, normalized_title)
        if best_external:
            return best_external
        if page_lookup:
            return page_lookup
        return None

    async def _lookup_from_known_page(
        self,
        title: str,
        paper_url: str | None,
        source_page_url: str | None,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        candidate_url = paper_url or source_page_url
        if not candidate_url:
            return None

        parsed = urlparse(candidate_url)
        domain = parsed.netloc.lower()
        try:
            if "ndss-symposium.org" in domain:
                return await self._lookup_ndss_page(candidate_url, title, venue=venue, year=year)
            if "usenix.org" in domain:
                return await self._lookup_usenix_page(candidate_url, title, venue=venue, year=year)
            if "ieeexplore.ieee.org" in domain:
                return await self._lookup_ieee_page(candidate_url, title, venue=venue, year=year)
            if "dl.acm.org" in domain:
                return await self._lookup_acm_page(candidate_url, title, venue=venue, year=year)
        except httpx.HTTPError:
            return None
        return None

    async def _lookup_ndss_page(
        self,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        html = await self._fetch_html(url)
        if not html:
            return None
        return self._extract_ndss_page_metadata(html, url=url, title=title, venue=venue, year=year)

    async def _lookup_usenix_page(
        self,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        html = await self._fetch_html(url)
        if not html:
            return None
        return self._extract_usenix_page_metadata(html, url=url, title=title, venue=venue, year=year)

    async def _lookup_ieee_page(
        self,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        html = await self._fetch_html(url)
        if not html:
            return None
        return self._extract_ieee_page_metadata(html, url=url, title=title, venue=venue, year=year)

    async def _lookup_acm_page(
        self,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        html = await self._fetch_html(url)
        if not html:
            return None
        return self._extract_acm_page_metadata(html, url=url, title=title, venue=venue, year=year)

    async def _lookup_via_semantic_scholar(
        self,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        headers = {"User-Agent": self.settings.paper_fetch_user_agent}
        if self.settings.semantic_scholar_api_key:
            headers["x-api-key"] = self.settings.semantic_scholar_api_key

        params = {
            "query": title,
            "limit": 5,
            "fields": "title,abstract,year,venue,url,externalIds,openAccessPdf",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.settings.http_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get("https://api.semanticscholar.org/graph/v1/paper/search", params=params)

        if response.status_code == 429:
            return None
        response.raise_for_status()

        payload = response.json()
        results = payload.get("data", [])
        return self._pick_semantic_scholar_match(results, title=title, venue=venue, year=year)

    async def _lookup_via_openalex(
        self,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        headers = {"User-Agent": self.settings.paper_fetch_user_agent}
        params = {
            "search": title,
            "per-page": 5,
            "select": ",".join(
                [
                    "display_name",
                    "publication_year",
                    "ids",
                    "primary_location",
                    "open_access",
                    "best_oa_location",
                    "abstract_inverted_index",
                ]
            ),
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
        return self._pick_openalex_match(results, title=title, venue=venue, year=year)

    async def _fetch_html(self, url: str) -> str | None:
        headers = {"User-Agent": self.settings.paper_fetch_user_agent}
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.settings.http_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        return response.text

    def _merge_lookup_results(
        self,
        page_result: PaperLookupResult,
        external_result: PaperLookupResult,
        normalized_title: str,
    ) -> PaperLookupResult:
        merged = PaperLookupResult(
            provider=f"{page_result.provider}+{external_result.provider}",
            confidence=max(page_result.confidence, external_result.confidence),
            title=external_result.title or page_result.title,
            abstract=external_result.abstract or page_result.abstract,
            url=page_result.url or external_result.url,
            source_page_url=page_result.source_page_url or external_result.source_page_url,
            pdf_url=page_result.pdf_url or external_result.pdf_url,
            preprint_pdf_url=page_result.preprint_pdf_url or external_result.preprint_pdf_url,
            slide_url=page_result.slide_url or external_result.slide_url,
            video_url=page_result.video_url or external_result.video_url,
            venue=page_result.venue or external_result.venue,
            year=page_result.year or external_result.year,
            doi=external_result.doi or page_result.doi,
            external_ids={**external_result.external_ids, **page_result.external_ids},
            notes=[*page_result.notes, *external_result.notes],
        )
        if merged.title:
            merged.confidence = max(
                merged.confidence,
                self._score_candidate(
                    normalized_title,
                    self._normalize_title(merged.title),
                    year=merged.year,
                    expected_year=merged.year,
                    venue=merged.venue,
                    expected_venue=merged.venue,
                ),
            )
        return merged

    def _extract_ndss_page_metadata(
        self,
        html: str,
        *,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=True)
        normalized_title = self._normalize_title(title)
        page_title = self.abstract_fetcher._clean_text(  # pyright: ignore[reportPrivateUsage]
            soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else title
        )
        abstract = self.abstract_fetcher._extract_abstract(html)  # pyright: ignore[reportPrivateUsage]

        pdf_url: str | None = None
        slide_url: str | None = None
        video_url: str | None = None

        for anchor in anchors:
            href = urljoin(url, anchor["href"])
            label = self._normalize_title(anchor.get_text(" ", strip=True))
            if "youtube.com" in href or "youtu.be" in href:
                video_url = video_url or href
                continue
            if not href.lower().endswith(".pdf"):
                continue
            if "slide" in label:
                slide_url = slide_url or href
                continue
            if "paper" in label:
                pdf_url = pdf_url or href
                continue
            if pdf_url is None:
                pdf_url = href
            elif slide_url is None:
                slide_url = href

        return PaperLookupResult(
            provider="ndss_page",
            confidence=self._score_candidate(
                normalized_title,
                self._normalize_title(page_title or title),
                year=year,
                expected_year=year,
                venue=venue,
                expected_venue=venue,
            ),
            title=page_title or title,
            abstract=abstract,
            url=url,
            source_page_url=url,
            pdf_url=pdf_url,
            slide_url=slide_url,
            video_url=video_url,
            venue=venue or "NDSS Symposium",
            year=year,
            notes=["Metadata extracted from the NDSS paper page."],
        )

    def _extract_usenix_page_metadata(
        self,
        html: str,
        *,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=True)
        iframes = soup.find_all("iframe", src=True)
        normalized_title = self._normalize_title(title)
        page_title = self.abstract_fetcher._clean_text(  # pyright: ignore[reportPrivateUsage]
            soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else title
        )
        abstract = self.abstract_fetcher._extract_abstract(html)  # pyright: ignore[reportPrivateUsage]

        pdf_url: str | None = None
        preprint_pdf_url: str | None = None
        slide_url: str | None = None
        video_url: str | None = None

        for iframe in iframes:
            src = iframe.get("src")
            if not src:
                continue
            resolved = urljoin(url, src)
            if "youtube.com/embed/" in resolved or "youtu.be/" in resolved:
                video_url = resolved
                break

        for anchor in anchors:
            href = urljoin(url, anchor["href"])
            label = self._normalize_title(anchor.get_text(" ", strip=True))
            if ("youtube.com/watch" in href or "youtu.be/" in href) and not video_url:
                video_url = video_url or href
                continue
            if not href.lower().endswith(".pdf"):
                continue
            href_lower = href.lower()
            if "prepub" in href_lower:
                preprint_pdf_url = preprint_pdf_url or href
                continue
            if "slide" in label or "_slides" in href_lower:
                slide_url = slide_url or href
                continue
            pdf_url = pdf_url or href

        return PaperLookupResult(
            provider="usenix_page",
            confidence=self._score_candidate(
                normalized_title,
                self._normalize_title(page_title or title),
                year=year,
                expected_year=year,
                venue=venue,
                expected_venue=venue,
            ),
            title=page_title or title,
            abstract=abstract,
            url=url,
            source_page_url=url,
            pdf_url=pdf_url,
            preprint_pdf_url=preprint_pdf_url,
            slide_url=slide_url,
            video_url=video_url,
            venue=venue or "USENIX Security",
            year=year,
            notes=["Metadata extracted from the USENIX paper page."],
        )

    def _extract_ieee_page_metadata(
        self,
        html: str,
        *,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult:
        soup = BeautifulSoup(html, "html.parser")
        normalized_title = self._normalize_title(title)
        page_title = (
            self.abstract_fetcher._clean_text(soup.title.get_text(" ", strip=True))  # pyright: ignore[reportPrivateUsage]
            if soup.title
            else title
        )
        meta_abstract = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        abstract = None
        if meta_abstract and meta_abstract.get("content"):
            abstract = self.abstract_fetcher._clean_text(meta_abstract["content"])  # pyright: ignore[reportPrivateUsage]

        document_id = self._extract_ieee_document_id(url)
        pdf_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={document_id}" if document_id else None

        doi = None
        for meta_name in ("citation_doi", "dc.Identifier"):
            meta = soup.find("meta", attrs={"name": meta_name})
            if meta and meta.get("content"):
                doi = self.abstract_fetcher._clean_text(meta["content"])  # pyright: ignore[reportPrivateUsage]
                break

        return PaperLookupResult(
            provider="ieee_page",
            confidence=self._score_candidate(
                normalized_title,
                self._normalize_title(page_title or title),
                year=year,
                expected_year=year,
                venue=venue,
                expected_venue=venue,
            ),
            title=page_title or title,
            abstract=abstract,
            url=url,
            source_page_url=url,
            pdf_url=pdf_url,
            venue=venue or "IEEE",
            year=year,
            doi=doi,
            notes=["Metadata extracted from the IEEE Xplore page."],
        )

    def _extract_acm_page_metadata(
        self,
        html: str,
        *,
        url: str,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult:
        soup = BeautifulSoup(html, "html.parser")
        normalized_title = self._normalize_title(title)
        page_title = self.abstract_fetcher._clean_text(  # pyright: ignore[reportPrivateUsage]
            soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else title
        )
        abstract = self.abstract_fetcher._extract_abstract(html)  # pyright: ignore[reportPrivateUsage]
        doi = self._extract_doi_from_acm_url(url)
        pdf_url = f"https://dl.acm.org/doi/pdf/{doi}" if doi else None

        return PaperLookupResult(
            provider="acm_page",
            confidence=self._score_candidate(
                normalized_title,
                self._normalize_title(page_title or title),
                year=year,
                expected_year=year,
                venue=venue,
                expected_venue=venue,
            ),
            title=page_title or title,
            abstract=abstract,
            url=url,
            source_page_url=url,
            pdf_url=pdf_url,
            venue=venue or "ACM",
            year=year,
            doi=doi,
            notes=["Metadata extracted from the ACM Digital Library page."],
        )

    def _pick_semantic_scholar_match(
        self,
        results: list[dict],
        *,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        normalized_title = self._normalize_title(title)
        best_result: PaperLookupResult | None = None
        best_score = 0.0

        for item in results:
            candidate_title = self.abstract_fetcher._clean_text(item.get("title", "") or "")  # pyright: ignore[reportPrivateUsage]
            if not candidate_title:
                continue
            candidate_year = item.get("year")
            candidate_venue = self.abstract_fetcher._clean_text(item.get("venue", "") or "")  # pyright: ignore[reportPrivateUsage]
            score = self._score_candidate(
                normalized_title,
                self._normalize_title(candidate_title),
                year=candidate_year,
                expected_year=year,
                venue=candidate_venue,
                expected_venue=venue,
            )
            if score <= best_score:
                continue

            external_ids = {
                key: value
                for key, value in (item.get("externalIds") or {}).items()
                if isinstance(value, str) and value
            }
            open_access_pdf = item.get("openAccessPdf") or {}
            best_score = score
            best_result = PaperLookupResult(
                provider="semantic_scholar",
                confidence=score,
                title=candidate_title,
                abstract=self.abstract_fetcher._clean_text(item.get("abstract", "") or ""),  # pyright: ignore[reportPrivateUsage]
                url=item.get("url"),
                pdf_url=open_access_pdf.get("url"),
                venue=candidate_venue,
                year=candidate_year,
                doi=external_ids.get("DOI"),
                external_ids=external_ids,
                notes=["Metadata returned by Semantic Scholar paper search."],
            )

        if best_score < 0.82:
            return None
        return best_result

    def _pick_openalex_match(
        self,
        results: list[dict],
        *,
        title: str,
        venue: str | None,
        year: int | None,
    ) -> PaperLookupResult | None:
        normalized_title = self._normalize_title(title)
        best_result: PaperLookupResult | None = None
        best_score = 0.0

        for item in results:
            candidate_title = self.abstract_fetcher._clean_text(item.get("display_name", "") or "")  # pyright: ignore[reportPrivateUsage]
            abstract = self.abstract_fetcher._extract_inverted_index_text(item.get("abstract_inverted_index"))  # pyright: ignore[reportPrivateUsage]
            if not candidate_title:
                continue

            candidate_year = item.get("publication_year")
            score = self._score_candidate(
                normalized_title,
                self._normalize_title(candidate_title),
                year=candidate_year,
                expected_year=year,
                venue=None,
                expected_venue=venue,
            )
            if score <= best_score:
                continue

            primary_location = item.get("primary_location") or {}
            best_oa_location = item.get("best_oa_location") or {}
            ids = item.get("ids") or {}
            best_score = score
            best_result = PaperLookupResult(
                provider="openalex",
                confidence=score,
                title=candidate_title,
                abstract=abstract,
                url=primary_location.get("landing_page_url") or best_oa_location.get("landing_page_url"),
                pdf_url=best_oa_location.get("pdf_url") or primary_location.get("pdf_url"),
                venue=None,
                year=candidate_year,
                doi=self._normalize_doi(ids.get("doi")),
                external_ids={
                    key.upper(): value
                    for key, value in ids.items()
                    if isinstance(value, str) and value
                },
                notes=["Metadata returned by OpenAlex work search."],
            )

        if best_score < 0.8:
            return None
        return best_result

    def _normalize_doi(self, value: str | None) -> str | None:
        if not value:
            return None
        return value.removeprefix("https://doi.org/").strip() or None

    def _extract_ieee_document_id(self, url: str) -> str | None:
        path = urlparse(url).path.strip("/")
        if path.startswith("document/"):
            document_id = path.removeprefix("document/").split("/", 1)[0]
            return document_id or None
        return None

    def _extract_doi_from_acm_url(self, url: str) -> str | None:
        path = urlparse(url).path.strip("/")
        if path.startswith("doi/"):
            doi = path.removeprefix("doi/").removeprefix("pdf/")
            return doi or None
        return None

    def _score_candidate(
        self,
        normalized_query_title: str,
        normalized_candidate_title: str,
        *,
        year: int | None,
        expected_year: int | None,
        venue: str | None,
        expected_venue: str | None,
    ) -> float:
        score = self._title_similarity(normalized_query_title, normalized_candidate_title)
        lowered = normalized_candidate_title.lower()

        for penalty_term in ("artifact evaluation", "supplementary", "poster", "demo", "appendix"):
            if penalty_term in lowered:
                score -= 0.18

        if expected_year and year and expected_year == year:
            score += 0.03
        elif expected_year and year and expected_year != year:
            score -= 0.06

        if expected_venue and venue:
            normalized_expected_venue = self._normalize_title(expected_venue)
            normalized_venue = self._normalize_title(venue)
            if normalized_expected_venue and normalized_expected_venue in normalized_venue:
                score += 0.03

        return max(0.0, min(score, 1.0))

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
