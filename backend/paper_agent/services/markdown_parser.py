import asyncio
import re
from dataclasses import dataclass
import json
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from paper_agent.config import get_settings

VENUE_PATTERN = re.compile(
    r"\b("
    r"neurips|iclr|icml|acl|emnlp|naacl|aaai|cvpr|eccv|iccv|colm|kdd|www|usenix security|"
    r"ieee s&p|oakland|ccs|ndss|raid|acsac"
    r")\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
TEXT_LINK_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+?)\s+[-:]\s+(https?://\S+)\s*$")
SOURCE_URL_PATTERN = re.compile(r"^\s*URL Source:\s*(https?://\S+)\s*$", re.IGNORECASE | re.MULTILINE)
MAX_REASONABLE_TITLE_CHARS = 500


class ImportJobCancelledError(Exception):
    pass


@dataclass(slots=True)
class ParsedPaper:
    title: str
    url: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None


@dataclass(slots=True)
class KnownConferenceLabel:
    name: str
    year: int | None = None
    source_page_url: str | None = None


class ParsedPaperRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None


class ParsedPaperList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papers: list[ParsedPaperRecord] = Field(default_factory=list)


def extract_document_source_url(content: str) -> str | None:
    match = SOURCE_URL_PATTERN.search(content)
    return match.group(1).strip() if match else None


def normalize_title_for_dedupe(title: str) -> str:
    lowered = title.lower()
    alnum_only = "".join(char if char.isalnum() else " " for char in lowered)
    return " ".join(alnum_only.split())


def split_markdown_into_chunks(
    content: str,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    if len(content) <= max_chars:
        return [content]

    lines = content.splitlines()
    prefix_text, body_lines = _extract_chunk_prefix_and_body(lines)

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for line in body_lines:
        line_length = len(line) + 1
        if current_lines and current_length + line_length > max_chars:
            chunk_body = "\n".join(current_lines).strip()
            if chunk_body:
                chunks.append(_compose_chunk(prefix_text, chunk_body))
            current_lines = _tail_lines_for_overlap(current_lines, overlap_chars)
            current_length = sum(len(item) + 1 for item in current_lines)

        current_lines.append(line)
        current_length += line_length

    chunk_body = "\n".join(current_lines).strip()
    if chunk_body:
        chunks.append(_compose_chunk(prefix_text, chunk_body))

    return chunks or [content]


def _compose_chunk(prefix_text: str, chunk_body: str) -> str:
    if prefix_text:
        return f"{prefix_text}\n\nMarkdown Content:\n{chunk_body}"
    return chunk_body


def _extract_chunk_prefix_and_body(lines: list[str]) -> tuple[str, list[str]]:
    prefix_lines: list[str] = []
    body_start = 0

    for index, line in enumerate(lines):
        if line.strip().lower() == "markdown content:":
            body_start = index + 1
            break
        prefix_lines.append(line)
    else:
        return "", lines

    prefix_text = "\n".join(prefix_lines).strip()
    body_lines = lines[body_start:]
    return prefix_text, body_lines


def _tail_lines_for_overlap(lines: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0:
        return []
    overlap_lines: list[str] = []
    total = 0
    for line in reversed(lines):
        overlap_lines.append(line)
        total += len(line) + 1
        if total >= overlap_chars:
            break
    return list(reversed(overlap_lines))


def _normalize_venue(raw_heading: str) -> str | None:
    match = VENUE_PATTERN.search(raw_heading)
    if not match:
        return None
    venue = match.group(1)
    mapping = {
        "neurips": "NeurIPS",
        "iclr": "ICLR",
        "icml": "ICML",
        "acl": "ACL",
        "emnlp": "EMNLP",
        "naacl": "NAACL",
        "aaai": "AAAI",
        "cvpr": "CVPR",
        "eccv": "ECCV",
        "iccv": "ICCV",
        "colm": "COLM",
        "kdd": "KDD",
        "www": "WWW",
        "usenix security": "USENIX Security",
        "ieee s&p": "IEEE S&P",
        "oakland": "IEEE S&P",
        "ccs": "CCS",
        "ndss": "NDSS",
        "raid": "RAID",
        "acsac": "ACSAC",
    }
    return mapping.get(venue.lower(), venue)


def _extract_context(heading: str) -> tuple[str | None, int | None]:
    venue = _normalize_venue(heading)
    year_match = YEAR_PATTERN.search(heading)
    year = int(year_match.group(1)) if year_match else None
    return venue, year


def normalize_parsed_papers(parsed: list[ParsedPaper]) -> list[ParsedPaper]:
    seen_keys: set[tuple[str, str]] = set()
    normalized: list[ParsedPaper] = []

    for item in parsed:
        url = item.url.strip() if item.url else None
        source_page_url = item.source_page_url.strip() if item.source_page_url else None
        title = re.sub(r"\s+", " ", item.title).strip()
        if len(title) > MAX_REASONABLE_TITLE_CHARS:
            continue
        normalized_title = normalize_title_for_dedupe(title)
        venue = item.venue.strip() if item.venue else None
        dedupe_key = ("url", url) if url else ("title_source", f"{normalized_title}::{source_page_url or ''}::{item.year or ''}")
        if not title or dedupe_key in seen_keys:
            continue
        normalized.append(
            ParsedPaper(
                title=title,
                url=url,
                source_page_url=source_page_url,
                venue=venue,
                year=item.year,
            )
        )
        seen_keys.add(dedupe_key)

    return normalized


def parse_markdown_papers_rule_based(content: str) -> list[ParsedPaper]:
    current_venue: str | None = None
    current_year: int | None = None
    document_source_url = extract_document_source_url(content)
    parsed: list[ParsedPaper] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            current_venue, current_year = _extract_context(stripped)
            continue

        markdown_match = MARKDOWN_LINK_PATTERN.search(stripped)
        text_match = TEXT_LINK_PATTERN.match(stripped)

        if markdown_match:
            title, url = markdown_match.groups()
        elif text_match:
            title, url = text_match.groups()
        else:
            continue

        parsed.append(
            ParsedPaper(
                title=title,
                url=url,
                source_page_url=document_source_url,
                venue=current_venue,
                year=current_year,
            )
        )

    return normalize_parsed_papers(parsed)


class MarkdownParser:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.settings = get_settings()
        self.client = client

    def _get_client(self) -> AsyncOpenAI:
        if self.client is None:
            self.client = AsyncOpenAI()
        return self.client

    def _response_schema(self) -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "papers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": ["string", "null"]},
                            "source_page_url": {"type": ["string", "null"]},
                            "venue": {"type": ["string", "null"]},
                            "year": {"type": ["integer", "null"]},
                        },
                        "required": ["title", "url", "source_page_url", "venue", "year"],
                    },
                }
            },
            "required": ["papers"],
        }

    async def parse_markdown_papers(
        self,
        content: str,
        existing_conferences: list[KnownConferenceLabel] | None = None,
        progress_callback: Callable[[int, int], Awaitable[None]] | None = None,
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> list[ParsedPaper]:
        fallback = parse_markdown_papers_rule_based(content)
        try:
            chunks = split_markdown_into_chunks(
                content,
                max_chars=self.settings.parser_chunk_size_chars,
                overlap_chars=self.settings.parser_chunk_overlap_chars,
            )
            total_chunks = len(chunks)
            completed_chunks = 0
            semaphore = asyncio.Semaphore(max(1, self.settings.parser_max_concurrency))

            async def parse_one(index: int, chunk: str) -> list[ParsedPaper]:
                nonlocal completed_chunks
                async with semaphore:
                    if cancel_check and await cancel_check():
                        raise ImportJobCancelledError()
                    chunk_result = await self._parse_chunk_with_llm(chunk, existing_conferences=existing_conferences)
                    if cancel_check and await cancel_check():
                        raise ImportJobCancelledError()
                    completed_chunks += 1
                    if progress_callback:
                        await progress_callback(completed_chunks, total_chunks)
                    return chunk_result

            chunk_results = await asyncio.gather(
                *(parse_one(index, chunk) for index, chunk in enumerate(chunks, start=1))
            )
            parsed = [paper for chunk_result in chunk_results for paper in chunk_result]
            normalized = normalize_parsed_papers(parsed)
            return normalized or fallback
        except ImportJobCancelledError:
            raise
        except Exception:
            return fallback

    async def _parse_chunk_with_llm(
        self,
        content: str,
        existing_conferences: list[KnownConferenceLabel] | None = None,
    ) -> list[ParsedPaper]:
        document_source_url = extract_document_source_url(content)
        response = await self._get_client().chat.completions.create(
            model=self.settings.openai_parser_model,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "parsed_paper_list",
                    "schema": self._response_schema(),
                    "strict": True,
                },
            },
            messages=[
                {
                    "role": "system",
                    "content": self._build_parser_system_prompt(existing_conferences or []),
                },
                {
                    "role": "user",
                    "content": content,
                },
            ],
        )

        raw_content = response.choices[0].message.content
        if not raw_content:
            return []
        parsed_output = ParsedPaperList.model_validate(json.loads(raw_content))

        return [
            ParsedPaper(
                title=item.title,
                url=item.url,
                source_page_url=item.source_page_url or document_source_url,
                venue=item.venue,
                year=item.year,
            )
            for item in parsed_output.papers
        ]

    def _build_parser_system_prompt(self, existing_conferences: list[KnownConferenceLabel]) -> str:
        lines = [
            "Extract paper records from markdown.",
            "Return every paper you can confidently identify.",
            "Preserve venue/year from headings or nearby context when present.",
            "Return title for every accepted paper you can identify.",
            "Paper URL is optional when the markdown only contains titles.",
            "If there is a page-level source URL, place it in source_page_url.",
            "The venue field should contain only the conference label itself.",
            "Do not append the year to venue unless the year is part of the official canonical conference name.",
            "If a year is available, put it in the separate year field instead of formatting venue like 'Conference Name (2026)'.",
            "If one of the existing conference labels matches the paper's conference, reuse that label with exactly the same spelling.",
            "If no existing conference label matches, infer a concise new conference label and return it in venue.",
        ]

        if existing_conferences:
            lines.append("Existing conference labels:")
            for conference in existing_conferences[:200]:
                detail = conference.name
                if conference.source_page_url:
                    detail = f"{detail} | source={conference.source_page_url}"
                if conference.year:
                    detail = f"{detail} | year={conference.year}"
                lines.append(f"- {detail}")

        return " ".join(lines[:11]) + ("\n" + "\n".join(lines[11:]) if len(lines) > 11 else "")
