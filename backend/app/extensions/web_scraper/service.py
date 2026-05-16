"""Unified scraping service - Provider dispatch layer."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Proxy configuration."""

    enabled: bool = False
    proxy_type: str = "http"
    host: str = ""
    port: int = 0
    username: str | None = None
    password: str | None = None
    country: str | None = None


@dataclass
class AuthConfig:
    """Authentication configuration."""

    enabled: bool = False
    auth_type: str = "basic"
    username: str | None = None
    password: str | None = None
    token: str | None = None
    cookies: dict | None = None
    headers: dict | None = None


@dataclass
class ScrapeConfig:
    """Scrape configuration."""

    url: str
    prompt: str = "Extract important information from the webpage, organize as Markdown."
    provider: str = "firecrawl"
    schema_name: str | None = None
    llm_model: str | None = None
    timeout: int = 120
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    max_retries: int = 3


@dataclass
class ScrapeResult:
    """Scrape result."""

    success: bool
    content: str | None = None
    structured_data: dict | None = None
    provider: str = ""
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseProvider(ABC):
    """Scrape provider abstract base class."""

    name: str = "base"
    supports_structured: bool = False

    @abstractmethod
    async def scrape(
        self,
        config: ScrapeConfig,
        event_callback: callable | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Execute web scraping."""
        pass

    @abstractmethod
    def supports_schema(self, schema: str | None) -> bool:
        """Check if provider supports the specified schema."""
        pass

    def _create_event(self, event_type: str, level: str, message: str, **kwargs) -> dict:
        """Create event object."""
        event = {"type": event_type, "level": level, "message": message}
        event.update(kwargs)
        return event




class JinaProvider(BaseProvider):
    """Jina Provider - fallback option."""

    name = "jina"
    supports_structured = False

    def supports_schema(self, schema: str | None) -> bool:
        return False

    async def scrape(
        self,
        config: ScrapeConfig,
        event_callback: callable | None = None,
    ) -> AsyncGenerator[dict, None]:
        yield self._create_event("log", "info", "Using Jina Provider (fallback mode)...")

        if config.schema_name:
            yield self._create_event("log", "warning", "Jina does not support structured extraction, returning raw Markdown")

        try:
            from deerflow.community.jina_ai.jina_client import JinaClient
            from deerflow.utils.readability import ReadabilityExtractor

            jina = JinaClient()
            readability = ReadabilityExtractor()

            yield self._create_event("log", "info", f"Fetching: {config.url}")

            html = await jina.crawl(config.url, return_format="html", timeout=30)

            if html.startswith("Error:"):
                raise Exception(html)

            article = readability.extract_article(html)
            markdown = article.to_markdown()

            yield self._create_event("result", "success", "Scraping complete", content=markdown)

        except ImportError as e:
            logger.error(f"Jina module import failed: {e}")
            yield self._create_event("error", "error", f"Jina module unavailable: {e}")
            raise
        except Exception as e:
            logger.error(f"Jina scraping failed: {e}")
            yield self._create_event("error", "error", str(e))
            raise


class FirecrawlProvider(BaseProvider):
    """Firecrawl Provider - primary scraping provider."""

    name = "firecrawl"
    supports_structured = False

    def supports_schema(self, schema: str | None) -> bool:
        return False

    async def scrape(
        self,
        config: ScrapeConfig,
        event_callback: callable | None = None,
    ) -> AsyncGenerator[dict, None]:
        yield self._create_event("log", "info", "Using Firecrawl Provider...")

        if config.schema_name:
            yield self._create_event("log", "warning", "Firecrawl does not support structured extraction, returning raw Markdown")

        try:
            from deerflow.community.firecrawl.tools import web_fetch_tool

            yield self._create_event("log", "info", f"Fetching: {config.url}")

            markdown = web_fetch_tool.invoke({"url": config.url})

            if markdown.startswith("Error:"):
                raise Exception(markdown)

            yield self._create_event("result", "success", "Scraping complete", content=markdown)

        except ImportError as e:
            logger.error(f"Firecrawl module import failed: {e}")
            yield self._create_event("error", "error", f"Firecrawl module unavailable: {e}")
            raise
        except Exception as e:
            logger.error(f"Firecrawl scraping failed: {e}")
            yield self._create_event("error", "error", str(e))
            raise


class ScraperService:
    """Unified scraping service - Provider dispatch."""

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {
            "firecrawl": FirecrawlProvider(),
            "jina": JinaProvider(),
        }
        self._fallback_order = ["firecrawl", "jina"]

    def get_providers(self) -> list[dict]:
        """Get available provider list."""
        return [
            {
                "name": p.name,
                "supports_structured": p.supports_structured,
                "is_primary": name == "firecrawl",
            }
            for name, p in self._providers.items()
        ]

    async def scrape(
        self,
        config: ScrapeConfig,
        auto_fallback: bool = True,
    ) -> AsyncGenerator[dict, None]:
        """Execute scraping with automatic fallback."""
        providers = [config.provider] if not auto_fallback else self._fallback_order

        last_error = None
        for provider_name in providers:
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            if config.schema_name and not provider.supports_structured:
                yield self._create_event("log", "info", f"{provider.name} does not support structured extraction, returning raw Markdown")

            yield self._create_event("log", "info", f"Trying {provider.name}...")

            try:
                async for event in provider.scrape(config):
                    event["provider_used"] = provider.name
                    yield event

                return

            except Exception as e:
                last_error = e
                yield self._create_event("log", "warning", f"{provider.name} failed: {e}")
                continue

        yield self._create_event("error", "error", f"All providers failed: {last_error}", final=True)

    def _create_event(self, event_type: str, level: str, message: str, **kwargs) -> dict:
        event = {"type": event_type, "level": level, "message": message}
        event.update(kwargs)
        return event


scraper_service = ScraperService()
