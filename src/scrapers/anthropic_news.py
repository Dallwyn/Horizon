"""Anthropic news listing scraper.

Anthropic publishes no RSS/Atom feed for https://www.anthropic.com/news, so
this scraper parses the listing page's server-rendered HTML directly and
follows each `/news/<slug>` link found there.

Design notes:

* The listing only exposes day-granularity dates (e.g. "Aug 14, 2026"), with
  no time-of-day component. That is too coarse to gate inclusion against a
  rolling `since` cutoff without either missing same-day items published
  after the cutoff, or re-emitting the same item across consecutive daily
  runs. Novelty is therefore tracked by persisting seen slugs to
  `<data-dir>/anthropic_seen_slugs.json` rather than by published-date
  filtering; `since` is not used to gate inclusion at all.
* Selectors match by structural relationship (a link starting with
  `/news/`, plus the nearest `<time>` / title / category element) instead
  of exact CSS module class names, since those hashed class names can
  change across Anthropic site redeploys.
* Optional `content_extractor` (e.g. `trafilatura`) fetches full article
  text; if unset or extraction fails, the item falls back to title-only
  content rather than aborting, matching the RSS scraper's fallback
  behavior.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .._file_utils import _atomic_write_text
from ..extractors import ExtractorRegistry
from ..models import AnthropicNewsConfig, ContentItem, SourceType
from .base import BaseScraper

logger = logging.getLogger(__name__)

_SEEN_SLUGS_LIMIT = 500  # bound file growth; oldest slugs drop off first
_SLUG_HREF_RE = re.compile(r"^/news/([a-z0-9][a-z0-9-]*)/?$")
_DATE_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},\s+\d{4}\b"
)


class AnthropicNewsScraper(BaseScraper):
    """Scraper for the Anthropic news listing page."""

    SOURCE_TYPE = SourceType.ANTHROPIC

    def __init__(
        self,
        config: AnthropicNewsConfig,
        http_client: httpx.AsyncClient,
        state_path: Path,
        extractors: Optional[ExtractorRegistry] = None,
    ):
        """Initialize the scraper.

        Args:
            config: Anthropic news source configuration.
            http_client: Shared async HTTP client.
            state_path: Path to the persisted seen-slugs JSON file.
            extractors: Optional registry of content extractors for full
                article fetching.
        """
        super().__init__({"anthropic": config}, http_client)
        self.news_config = config
        self.state_path = state_path
        self._extractors = extractors

    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch currently-listed articles not seen in a previous run.

        `since` is accepted for interface consistency with other scrapers
        but is not used to gate inclusion; see module docstring.
        """
        if not self.news_config.enabled:
            return []

        try:
            response = await self.client.get(
                self.news_config.url, follow_redirects=True
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Error fetching Anthropic news listing: %s", exc)
            return []

        try:
            entries = self._parse_listing(response.text)
        except Exception as exc:
            logger.warning("Error parsing Anthropic news listing: %s", exc)
            return []

        entries = entries[: self.news_config.max_items]
        seen = self._load_seen_slugs()
        new_entries = [e for e in entries if e["slug"] not in seen]

        items: List[ContentItem] = []
        for entry in new_entries:
            content = entry["title"]
            if self.news_config.content_extractor and self._extractors:
                extractor = self._extractors.get(self.news_config.content_extractor)
                if extractor:
                    full = await extractor.extract(entry["url"], self.client)
                    if full:
                        content = full

            meta = {
                "category": entry.get("category") or self.news_config.category,
            }
            items.append(
                ContentItem(
                    id=self._generate_id("anthropic", "news", entry["slug"]),
                    source_type=self.SOURCE_TYPE,
                    title=entry["title"],
                    url=entry["url"],
                    content=content,
                    author="Anthropic",
                    published_at=entry["published_at"],
                    profile=self.news_config.profile,
                    metadata={k: v for k, v in meta.items() if v is not None},
                )
            )

        if new_entries:
            self._save_seen_slugs(seen | {e["slug"] for e in new_entries})

        return items

    def _parse_listing(self, html: str) -> List[dict]:
        """Extract (slug, url, title, category, published_at) per news link."""
        soup = BeautifulSoup(html, "html.parser")
        now = datetime.now(timezone.utc)
        seen_slugs_on_page: set[str] = set()
        entries: List[dict] = []

        for link in soup.find_all("a", href=_SLUG_HREF_RE):
            href = link.get("href", "")
            match = _SLUG_HREF_RE.match(href)
            if not match:
                continue
            slug = match.group(1)
            if slug in seen_slugs_on_page:
                continue  # the same article can appear in a "featured" block and the archive list
            seen_slugs_on_page.add(slug)

            container = link.find_parent("li") or link
            title = self._extract_title(link, container)
            if not title:
                continue

            time_tag = container.find("time")
            published_at = self._parse_date(
                time_tag.get_text(strip=True) if time_tag else ""
            ) or now

            category = self._extract_category(container)

            entries.append(
                {
                    "slug": slug,
                    "url": urljoin(self.news_config.url, href),
                    "title": title,
                    "category": category,
                    "published_at": published_at,
                }
            )

        return entries

    @staticmethod
    def _extract_title(link, container) -> str:
        # Prefer a heading inside the link (featured grid uses h2 for the
        # primary card and h4 for smaller "side" cards), then a
        # title-labelled span inside the containing item (archive list).
        heading = link.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading and heading.get_text(strip=True):
            return heading.get_text(strip=True)
        title_span = container.find(
            "span", class_=lambda c: c and "title" in c.lower()
        )
        if title_span and title_span.get_text(strip=True):
            return title_span.get_text(strip=True)
        text = link.get_text(strip=True)
        return text or ""

    @staticmethod
    def _extract_category(container) -> Optional[str]:
        subject = container.find(
            "span", class_=lambda c: c and "subject" in c.lower()
        )
        if subject:
            text = subject.get_text(strip=True)
            return text or None
        return None

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        match = _DATE_RE.search(text or "")
        if not match:
            return None
        try:
            # Anthropic renders dates as day-granularity only; anchor to
            # midday UTC so the value is a reasonable display timestamp
            # without implying false precision either at day start or end.
            parsed = datetime.strptime(match.group(0), "%b %d, %Y")
        except ValueError:
            return None
        return parsed.replace(hour=12, tzinfo=timezone.utc)

    def _load_seen_slugs(self) -> set[str]:
        if not self.state_path.exists():
            return set()
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
        except (json.JSONDecodeError, OSError):
            pass
        return set()

    def _save_seen_slugs(self, slugs: set[str]) -> None:
        # No per-slug ordering is tracked, so on overflow we keep an
        # arbitrary (but bounded) subset rather than a strict LRU set.
        capped = list(slugs)[-_SEEN_SLUGS_LIMIT:]
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(self.state_path, json.dumps(capped, indent=2))
