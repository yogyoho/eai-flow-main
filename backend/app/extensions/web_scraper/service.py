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
    provider: str = "browser_use_local"
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


class BrowserUseLocalProvider(BaseProvider):
    """Browser Use local version Provider."""

    name = "browser_use_local"
    supports_structured = True

    def supports_schema(self, schema: str | None) -> bool:
        return True

    async def scrape(
        self,
        config: ScrapeConfig,
        event_callback: callable | None = None,
    ) -> AsyncGenerator[dict, None]:
        yield self._create_event("log", "info", "Using Browser Use local (self-hosted)...")

        try:
            import asyncio
            import os
            import shutil

            from browser_use import Agent, Browser
            from browser_use.browser import BrowserProfile

            task = self._build_task(config)

            schema_class = None
            if config.schema_name:
                from app.extensions.web_scraper.predefined_schemas import get_schema_by_name

                schema_class = get_schema_by_name(config.schema_name)
                if schema_class:
                    yield self._create_event("log", "info", f"Applying structured schema: {config.schema_name}")

            llm = self._create_llm(config.llm_model)
            if config.llm_model:
                yield self._create_event("log", "info", f"Using LLM model: {config.llm_model}")
            yield self._create_event("log", "info", f"Accessing: {config.url}")

            chromium_path = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")
            if not os.path.exists(chromium_path):
                chromium_path = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
                if not chromium_path:
                    raise RuntimeError(f"Chrome/Chromium not installed or not in PATH: {chromium_path}")

            try:
                proc = await asyncio.create_subprocess_exec(
                    chromium_path,
                    "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=2.0)
                except TimeoutError:
                    proc.kill()
                    raise RuntimeError("Chrome startup timeout (--version not executed within 2 seconds)")
                if proc.returncode != 0:
                    raise RuntimeError(f"Chrome --version returned non-zero status: {proc.returncode}")
            except Exception as e:
                raise RuntimeError(f"Chrome not available: {e}")

            profile = BrowserProfile(
                headless=True,
                disable_extensions=True,
                chromium_sandbox=False,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--mute-audio",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                ],
            )
            browser = Browser(
                browser_profile=profile,
                executable_path=chromium_path,
            )

            if "DISPLAY" not in os.environ or not os.environ.get("DISPLAY"):
                os.environ["DISPLAY"] = ":99"

            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
            )

            result = await agent.run()
            history_result = result

            if schema_class and hasattr(history_result, "structured_output") and history_result.structured_output:
                content = self._to_markdown(history_result.structured_output)
                yield self._create_event("result", "success", "Scraping complete", content=content, structured_data=history_result.structured_output)
                return

            if hasattr(history_result, "all_results") and history_result.all_results:
                errors_in_history = [r.error for r in history_result.all_results if r.error and "timed out" in str(r.error).lower()]
                if errors_in_history:
                    timeout_hint = "LLM call timed out (75s). Suggestions:\n1. Simplify prompt (e.g. only extract title and body)\n2. Check network and retry\n3. Switch to Jina / Firecrawl Provider"
                    logger.warning(f"Browser Use timeout: {errors_in_history[0]}")
                    yield self._create_event("error", "error", timeout_hint)
                    raise TimeoutError("LLM call timed out")

            extracted: str | None = None
            if hasattr(history_result, "extracted_content"):
                val = history_result.extracted_content
                extracted = val() if callable(val) else val
            if not extracted and hasattr(history_result, "final_result"):
                val = history_result.final_result
                extracted = val() if callable(val) else val

            if extracted:
                cleaned = self._clean_result_text(str(extracted))
                content = cleaned if cleaned else str(extracted)
                yield self._create_event("result", "success", "Scraping complete", content=content)
            else:
                extracted = self._extract_result(history_result)
                if extracted:
                    yield self._create_event("result", "success", "Scraping complete (from history)", content=extracted)
                else:
                    yield self._create_event("error", "error", "Agent returned no valid content. Try simplifying prompt or switching Provider.")
                    raise ValueError("Agent returned no valid content")

            try:
                if hasattr(browser, "reset"):
                    await browser.reset()
                elif hasattr(browser, "close"):
                    await browser.close()
            except Exception as e:
                logger.warning(f"Browser cleanup error (non-fatal): {e}")

        except ImportError as e:
            logger.exception("browser-use import failed")
            hint = f"browser-use import failed: {e}. Local dev: run uv sync or uv pip install browser-use in backend directory. Docker: backend/requirements.txt must include browser-use, then docker compose build gateway and restart."
            yield self._create_event("error", "error", hint)
            raise
        except Exception as e:
            error_msg = str(e)
            try:
                if "browser" in dir() and browser:
                    if hasattr(browser, "reset"):
                        await browser.reset()
                    elif hasattr(browser, "close"):
                        await browser.close()
            except Exception:
                pass

            browser_startup_errors = [
                "timed out",
                "Network is unreachable",
                "Chrome",
                "browser",
                "subprocess",
            ]
            is_browser_error = any(err in error_msg for err in browser_startup_errors)

            if is_browser_error:
                logger.warning(f"Browser Use failed (browser issue): {error_msg}")
            else:
                logger.error(f"Browser Use failed: {error_msg}")
            yield self._create_event("error", "error", error_msg)
            raise

    def _create_llm(self, model_name: str | None = None):
        """Create LLM instance from config.yaml ModelConfig."""
        if not model_name:
            raise ValueError("No LLM model specified, please configure models in config.yaml and select from frontend.")
        return self._create_llm_by_name(model_name)

    def _create_llm_by_name(self, model_name: str):
        """Find model from system ModelConfig and create browser-use LLM."""
        from app.gateway.config import get_gateway_config

        model_config = get_gateway_config().get_model_config(model_name)
        if model_config is None:
            raise ValueError(f"Model '{model_name}' not configured in config.yaml. Please add this model to the models list.")

        cfg = model_config.model_dump(exclude_none=True)
        meta_fields = {
            "name",
            "display_name",
            "description",
            "use",
            "supports_thinking",
            "supports_reasoning_effort",
            "when_thinking_enabled",
            "thinking",
            "supports_vision",
        }
        llm_kwargs = {k: v for k, v in cfg.items() if k not in meta_fields}

        use = model_config.use.lower()
        if "anthropic" in use or "claude" in use:
            from browser_use.llm.anthropic.chat import ChatAnthropic

            return ChatAnthropic(**llm_kwargs)
        elif "google" in use or "gemini" in use:
            from browser_use.llm.google.chat import ChatGoogle

            return ChatGoogle(**llm_kwargs)
        else:
            from browser_use.llm.openai.chat import ChatOpenAI

            if "max_tokens" in llm_kwargs:
                llm_kwargs["max_completion_tokens"] = llm_kwargs.pop("max_tokens")
            if llm_kwargs.get("base_url"):
                logger.info(f"Browser Use using custom endpoint: {llm_kwargs['base_url']}")
            return ChatOpenAI(**llm_kwargs)

    def _extract_result(self, history) -> str:
        """Extract result from Agent history."""
        if not history:
            return ""

        if hasattr(history, "steps"):
            steps = history.steps
        elif hasattr(history, "actions"):
            steps = history.actions
        else:
            return str(history)

        results = []
        for step in steps:
            if hasattr(step, "result") and step.result:
                if isinstance(step.result, str):
                    results.append(step.result)
                elif hasattr(step.result, "content"):
                    results.append(str(step.result.content))

        if results:
            return "\n\n".join(results)
        return ""

    def _build_task(self, config: ScrapeConfig) -> str:
        from app.extensions.web_scraper.predefined_schemas import get_schema_prompt

        if config.schema_name:
            prompt = get_schema_prompt(config.schema_name)
        else:
            prompt = config.prompt

        return f"Please visit {config.url} and complete the following task:\n\n{prompt}\n\nAfter completion, organize results as Markdown format and return."

    def _format_proxy(self, proxy: ProxyConfig) -> str:
        auth = ""
        if proxy.username and proxy.password:
            auth = f"{proxy.username}:{proxy.password}@"
        return f"{proxy.proxy_type}://{auth}{proxy.host}:{proxy.port}"

    def _clean_result_text(self, raw: str) -> str:
        """Clean browser-use raw output to extract clean Markdown body."""
        if not raw:
            return ""
        lines = raw.strip().split("\n")

        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("# ") or line.startswith("## "):
                return "\n".join(lines[i:]).strip()

        noise_prefixes = (
            "<url>",
            "<query>",
            "<result>",
            "<done>",
            "<error>",
            "🔗",
            "✅",
            "❌",
            "⚠️",
        )
        cleaned = [l for l in lines if not l.strip().startswith(noise_prefixes) and l.strip()]
        return "\n".join(cleaned[-50:]).strip()

    def _to_markdown(self, data) -> str:
        """Convert structured data to Markdown."""
        if hasattr(data, "model_dump"):
            data = data.model_dump()

        lines = ["# Web Data Extraction Report", ""]

        def format_value(val, indent=0):
            if isinstance(val, dict):
                for k, v in val.items():
                    lines.append(f"{'  ' * indent}- **{k}**: {format_value(v, indent + 1)}")
            elif isinstance(val, list):
                for item in val:
                    lines.append(f"{'  ' * indent}- {format_value(item, indent + 1)}")
            else:
                lines.append(str(val))

        format_value(data)
        return "\n".join(lines)


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
            from app.extensions.community.jina_ai.jina_client import JinaClient
            from app.extensions.community.readability.readability_extractor import ReadabilityExtractor

            jina = JinaClient()
            readability = ReadabilityExtractor()

            yield self._create_event("log", "info", f"Fetching: {config.url}")

            html = jina.crawl(config.url, return_format="html", timeout=30)

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
    """Firecrawl Provider - fallback option."""

    name = "firecrawl"
    supports_structured = False

    def supports_schema(self, schema: str | None) -> bool:
        return False

    async def scrape(
        self,
        config: ScrapeConfig,
        event_callback: callable | None = None,
    ) -> AsyncGenerator[dict, None]:
        yield self._create_event("log", "info", "Using Firecrawl Provider (fallback mode)...")

        if config.schema_name:
            yield self._create_event("log", "warning", "Firecrawl does not support structured extraction")

        try:
            from app.extensions.community.firecrawl.tools import web_fetch_tool

            yield self._create_event("log", "info", f"Fetching: {config.url}")

            markdown = web_fetch_tool(config.url)

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
            "browser_use_local": BrowserUseLocalProvider(),
            "jina": JinaProvider(),
            "firecrawl": FirecrawlProvider(),
        }
        self._fallback_order = ["jina", "firecrawl", "browser_use_local"]

    def get_providers(self) -> list[dict]:
        """Get available provider list."""
        return [
            {
                "name": p.name,
                "supports_structured": p.supports_structured,
                "is_primary": name == "browser_use_local",
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
                yield self._create_event("log", "info", f"{provider.name} does not support structured extraction, skipping")
                continue

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

        yield self._create_event("error", "error", f"All providers failed: {last_error}")

    def _create_event(self, event_type: str, level: str, message: str, **kwargs) -> dict:
        event = {"type": event_type, "level": level, "message": message}
        event.update(kwargs)
        return event


scraper_service = ScraperService()
