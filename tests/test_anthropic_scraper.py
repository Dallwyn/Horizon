from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx

from src.models import AnthropicNewsConfig
from src.scrapers.anthropic_news import AnthropicNewsScraper


SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Minimal fixtures mirroring the two real markup shapes on anthropic.com/news:
# a "featured" card (title/date nested inside the <a>, no <li> ancestor) and
# an archive "publication list" item (title/date as siblings inside <li><a>).
_FEATURED_ITEM = """
<a href="/news/claude-opus-5" class="content">
  <h2 class="featuredTitle">Introducing Claude Opus 5</h2>
  <div class="meta"><span class="caption">Product</span>
  <time class="date">Jul 24, 2026</time></div>
</a>
"""

_LIST_ITEM = """
<li><a href="/news/tino-cuellar" class="listItem">
  <div class="meta"><time class="date">Aug 4, 2026</time>
  <span class="subject">Announcements</span></div>
  <span class="title">Tino Cuellar joins Anthropic</span>
</a></li>
"""


def _listing_html(*items: str) -> str:
    return f"<html><body>{''.join(items)}</body></html>"


def _mock_client(html: str) -> AsyncMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.get.return_value = response
    return client


def _scraper(client, tmp_path: Path, **overrides) -> AnthropicNewsScraper:
    config = AnthropicNewsConfig(enabled=True, **overrides)
    return AnthropicNewsScraper(
        config, client, state_path=tmp_path / "anthropic_seen_slugs.json"
    )


def test_parses_featured_and_list_items(tmp_path: Path) -> None:
    client = _mock_client(_listing_html(_FEATURED_ITEM, _LIST_ITEM))
    scraper = _scraper(client, tmp_path)

    items = asyncio.run(scraper.fetch(SINCE))

    assert len(items) == 2
    by_url = {str(i.url): i for i in items}
    featured = by_url["https://www.anthropic.com/news/claude-opus-5"]
    assert featured.title == "Introducing Claude Opus 5"
    assert featured.published_at == datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert featured.author == "Anthropic"
    assert featured.id == "anthropic:news:claude-opus-5"

    listed = by_url["https://www.anthropic.com/news/tino-cuellar"]
    assert listed.title == "Tino Cuellar joins Anthropic"
    assert listed.metadata["category"] == "Announcements"
    assert listed.published_at == datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_same_slug_appearing_twice_on_page_is_emitted_once(tmp_path: Path) -> None:
    # The same article commonly appears in both the featured grid and the
    # archive list; it must not be emitted twice from a single fetch.
    duplicate_list_item = _LIST_ITEM.replace(
        '/news/tino-cuellar', '/news/claude-opus-5'
    )
    client = _mock_client(_listing_html(_FEATURED_ITEM, duplicate_list_item))
    scraper = _scraper(client, tmp_path)

    items = asyncio.run(scraper.fetch(SINCE))

    assert len(items) == 1


def test_seen_slugs_persist_across_runs(tmp_path: Path) -> None:
    html = _listing_html(_FEATURED_ITEM, _LIST_ITEM)

    first_client = _mock_client(html)
    first_items = asyncio.run(_scraper(first_client, tmp_path).fetch(SINCE))
    assert len(first_items) == 2

    state_path = tmp_path / "anthropic_seen_slugs.json"
    assert state_path.exists()
    stored = json.loads(state_path.read_text())
    assert set(stored) == {"claude-opus-5", "tino-cuellar"}

    # Second run against the unchanged listing must not re-emit either item.
    second_client = _mock_client(html)
    second_items = asyncio.run(_scraper(second_client, tmp_path).fetch(SINCE))
    assert second_items == []


def test_only_new_slug_emitted_when_listing_grows(tmp_path: Path) -> None:
    state_path = tmp_path / "anthropic_seen_slugs.json"
    state_path.write_text(json.dumps(["tino-cuellar"]))

    client = _mock_client(_listing_html(_FEATURED_ITEM, _LIST_ITEM))
    items = asyncio.run(_scraper(client, tmp_path).fetch(SINCE))

    assert len(items) == 1
    assert items[0].id == "anthropic:news:claude-opus-5"


def test_disabled_config_returns_empty(tmp_path: Path) -> None:
    client = _mock_client(_listing_html(_FEATURED_ITEM))
    config = AnthropicNewsConfig(enabled=False)
    scraper = AnthropicNewsScraper(
        config, client, state_path=tmp_path / "state.json"
    )

    assert asyncio.run(scraper.fetch(SINCE)) == []


def test_http_error_returns_empty(tmp_path: Path) -> None:
    client = AsyncMock()
    client.get.side_effect = httpx.HTTPError("boom")
    scraper = _scraper(client, tmp_path)

    assert asyncio.run(scraper.fetch(SINCE)) == []


def test_max_items_caps_listing(tmp_path: Path) -> None:
    many_items = "".join(
        _LIST_ITEM.replace("tino-cuellar", f"slug-{i}") for i in range(5)
    )
    client = _mock_client(_listing_html(many_items))
    scraper = _scraper(client, tmp_path, max_items=2)

    items = asyncio.run(scraper.fetch(SINCE))

    assert len(items) == 2


def test_malformed_html_does_not_crash(tmp_path: Path) -> None:
    client = _mock_client("<html><body><a href='/news/'>empty slug</a>not closed")
    scraper = _scraper(client, tmp_path)

    assert asyncio.run(scraper.fetch(SINCE)) == []


def test_content_extractor_used_when_configured(tmp_path: Path) -> None:
    client = _mock_client(_listing_html(_LIST_ITEM))

    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value="Full article text")
    registry = MagicMock()
    registry.get.return_value = extractor

    config = AnthropicNewsConfig(enabled=True, content_extractor="full-text")
    scraper = AnthropicNewsScraper(
        config,
        client,
        state_path=tmp_path / "state.json",
        extractors=registry,
    )

    items = asyncio.run(scraper.fetch(SINCE))

    assert len(items) == 1
    assert items[0].content == "Full article text"
    extractor.extract.assert_awaited_once()


def test_extraction_failure_falls_back_to_title(tmp_path: Path) -> None:
    client = _mock_client(_listing_html(_LIST_ITEM))

    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=None)
    registry = MagicMock()
    registry.get.return_value = extractor

    config = AnthropicNewsConfig(enabled=True, content_extractor="full-text")
    scraper = AnthropicNewsScraper(
        config,
        client,
        state_path=tmp_path / "state.json",
        extractors=registry,
    )

    items = asyncio.run(scraper.fetch(SINCE))

    assert len(items) == 1
    assert items[0].content == "Tino Cuellar joins Anthropic"
