import os
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.pipeline.config import PipelineConfig
from src.pipeline.framework import agent_tool
from src.pipeline.http_client import fetch_page
from src.pipeline.llm import chat_json
from src.pipeline.models import CandidateRecord
from src.pipeline.prompt_templates import render_prompt_file
from src.pipeline.queueing import enqueue_candidate
from src.pipeline.source_registry import mark_source_visited, upsert_source_page

YANDEX_SEARCH_URL = "https://yandex.eu/search/"
YANDEX_SEARCH_URLS = (YANDEX_SEARCH_URL, "https://yandex.com/search/", "https://yandex.ru/search/")
YANDEX_HOST_SUFFIXES = ("yandex.com", "yandex.eu", "yandex.ru")
YANDEX_INTERNAL_HOST_MARKERS = ("yandex.", "yandexcloud.")
SEARCH_USER_AGENT = "ai-web-scraping-pipeline/0.1"
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"


class SearchProviderError(RuntimeError):
    provider: str
    status: str

    def __init__(self, provider: str, status: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status


class SearchProviderBlockedError(SearchProviderError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(provider, "blocked_or_challenged", message)


class SearchProviderConfigurationError(SearchProviderError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(provider, "not_configured", message)


def normalize_generated_queries(payload: Any, limit: int) -> list[str]:
    values = payload.get("queries") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        return []

    queries: list[str] = []
    for value in values:
        query = str(value or "").strip()
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= limit:
            break
    return queries


def generate_search_queries(config: PipelineConfig, source_urls: list[str] | None = None) -> list[str]:
    deployment = os.getenv(config.llm.deploymentNameEnv)
    if not deployment:
        raise RuntimeError(f"Set {config.llm.deploymentNameEnv} before generating discovery search queries.")

    max_query_count = max(1, config.sourceDiscovery.generatedSearchQueryCount)
    prompt_values = {
        "domainDescription": config.domainDescription,
        "recordType": config.recordType,
        "schemaJson": [field.model_dump() for field in config.recordSchema.fields],
        "allowedDomains": config.sourceDiscovery.allowedDomains,
        "seedUrls": source_urls or config.sourceDiscovery.seedUrls,
        "maxQueryCount": max_query_count,
    }
    system_prompt = render_prompt_file(config.prompts.discoverySystem, prompt_values)
    user_prompt = render_prompt_file(config.prompts.discoveryUser, prompt_values)
    payload = chat_json(
        system_prompt,
        user_prompt,
        deployment=deployment,
        temperature=config.llm.temperature,
        agent_name="discovery-agent",
        tools=[search_google_tool, search_yandex_tool],
    )
    queries = normalize_generated_queries(payload, max_query_count)
    if not queries:
        raise RuntimeError("Discovery query generation returned no usable search queries.")
    return queries


def is_allowed_url(url: str, allowed_domains: list[str], blocked_domains: list[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    if any(hostname.endswith(domain.lower()) for domain in blocked_domains):
        return False
    return not allowed_domains or any(hostname.endswith(domain.lower()) for domain in allowed_domains)


def _unwrap_yandex_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.endswith(YANDEX_HOST_SUFFIXES):
        return url

    query = parse_qs(parsed.query)
    for key in ("url", "u", "target"):
        if query.get(key):
            return unquote(query[key][0])
    return url


def extract_yandex_result_urls(html: str, base_url: str = YANDEX_SEARCH_URL, limit: int = 10) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    results: list[str] = []
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, anchor["href"])
        unwrapped = _unwrap_yandex_url(absolute)
        parsed = urlparse(unwrapped)
        if parsed.scheme not in {"http", "https"}:
            continue
        hostname = (parsed.hostname or "").lower()
        if parsed.netloc.endswith(YANDEX_HOST_SUFFIXES) or any(marker in hostname for marker in YANDEX_INTERNAL_HOST_MARKERS):
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized not in results:
            results.append(normalized)
        if len(results) >= limit:
            break
    return results


def _is_yandex_challenge_page(html: str) -> bool:
    text = html.lower()
    return "smartcaptcha" in text or "showcaptcha" in text or "captcha" in text


def yandex_search(query: str, limit: int = 10, timeout: int = 20) -> list[str]:
    last_error: Exception | None = None
    challenged = False
    for search_url in YANDEX_SEARCH_URLS:
        try:
            response = requests.get(
                search_url,
                params={"text": query},
                timeout=timeout,
                headers={"User-Agent": SEARCH_USER_AGENT},
            )
            response.raise_for_status()
            if _is_yandex_challenge_page(response.text):
                challenged = True
                continue
            return extract_yandex_result_urls(response.text, response.url, limit=limit)
        except requests.RequestException as exc:
            last_error = exc
    if challenged:
        raise SearchProviderBlockedError("yandex", "Yandex returned a captcha or challenge page. Use curated seedUrls or Google Custom Search for reliable production discovery.")
    if last_error:
        raise last_error
    return []


@agent_tool(name="search_yandex", description="Run a low-volume Yandex web search and return discovered public result URLs as JSON.")
def search_yandex_tool(query: str, limit: int = 10) -> str:
    import json

    return json.dumps({"results": yandex_search(query, limit=limit)})


def extract_google_result_urls(payload: dict, limit: int = 10) -> list[str]:
    results: list[str] = []
    for item in payload.get("items") or []:
        link = item.get("link")
        if not link:
            continue
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"}:
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized not in results:
            results.append(normalized)
        if len(results) >= limit:
            break
    return results


def google_search(query: str, config: PipelineConfig, limit: int = 10, timeout: int = 20) -> list[str]:
    api_key = os.getenv(config.sourceDiscovery.googleApiKeyEnv)
    search_engine_id = os.getenv(config.sourceDiscovery.googleSearchEngineIdEnv)
    if not api_key or not search_engine_id:
        raise SearchProviderConfigurationError(
            "google",
            f"Set {config.sourceDiscovery.googleApiKeyEnv} and {config.sourceDiscovery.googleSearchEngineIdEnv} for Google Custom Search discovery.",
        )

    response = requests.get(
        GOOGLE_SEARCH_URL,
        params={"key": api_key, "cx": search_engine_id, "q": query, "num": max(1, min(limit, 10))},
        timeout=timeout,
        headers={"User-Agent": SEARCH_USER_AGENT},
    )
    response.raise_for_status()
    return extract_google_result_urls(response.json(), limit=limit)


@agent_tool(name="search_google", description="Run Google Custom Search and return discovered public result URLs as JSON.")
def search_google_tool(query: str, limit: int = 10) -> str:
    import json

    from src.pipeline.config import load_config

    return json.dumps({"results": google_search(query, load_config(), limit=limit)})


def _enqueue_if_allowed(
    link: str,
    discovered_from: str,
    config: PipelineConfig,
    queued: list[CandidateRecord],
    max_links: int,
) -> None:
    if len(queued) >= max_links:
        return
    if not is_allowed_url(link, config.sourceDiscovery.allowedDomains, config.sourceDiscovery.blockedDomains):
        return
    queued.append(enqueue_candidate(link, discovered_from=discovered_from))


def screen_sources(
    source_urls: list[str],
    max_links: int,
    config: PipelineConfig,
    search_queries: list[str] | None = None,
    search_provider: str | None = None,
    search_diagnostics: list[dict] | None = None,
) -> list[CandidateRecord]:
    queued: list[CandidateRecord] = []

    for source_url in source_urls:
        if len(queued) >= max_links:
            break
        upsert_source_page(source_url, config.sourceDiscovery.revisitFrequencyDays)
        page = fetch_page(source_url)
        for link in page.links:
            if len(queued) >= max_links:
                break
            _enqueue_if_allowed(link, source_url, config, queued, max_links)
        mark_source_visited(source_url, config.sourceDiscovery.revisitFrequencyDays)

    provider = search_provider or config.sourceDiscovery.searchProvider
    queries = config.sourceDiscovery.searchQueries if search_queries is None else search_queries
    if provider in {"yandex", "google"}:
        if not queries:
            try:
                queries = generate_search_queries(config, source_urls)
                if search_diagnostics is not None:
                    search_diagnostics.append({"provider": provider, "status": "queries_generated", "queries": queries})
            except Exception as exc:
                if search_diagnostics is not None:
                    search_diagnostics.append({"provider": provider, "status": "query_generation_failed", "message": str(exc)})
                return queued

        for query in queries:
            if len(queued) >= max_links:
                break
            try:
                links = (
                    yandex_search(query, limit=config.sourceDiscovery.searchMaxResults)
                    if provider == "yandex"
                    else google_search(query, config, limit=config.sourceDiscovery.searchMaxResults)
                )
                if search_diagnostics is not None:
                    search_diagnostics.append({"provider": provider, "query": query, "status": "ok", "resultCount": len(links)})
            except SearchProviderError as exc:
                if search_diagnostics is not None:
                    search_diagnostics.append({"provider": exc.provider, "query": query, "status": exc.status, "message": str(exc)})
                continue
            except requests.RequestException as exc:
                if search_diagnostics is not None:
                    search_diagnostics.append({"provider": provider, "query": query, "status": "request_failed", "message": str(exc)})
                continue

            for link in links:
                _enqueue_if_allowed(link, f"{provider}:{query}", config, queued, max_links)
                if len(queued) >= max_links:
                    break

    return queued
