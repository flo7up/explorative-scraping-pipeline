from urllib.parse import urlparse

from src.pipeline.config import PipelineConfig
from src.pipeline.http_client import fetch_page
from src.pipeline.models import CandidateRecord
from src.pipeline.queueing import enqueue_candidate
from src.pipeline.source_registry import mark_source_visited, upsert_source_page


def is_allowed_url(url: str, allowed_domains: list[str], blocked_domains: list[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    if any(hostname.endswith(domain.lower()) for domain in blocked_domains):
        return False
    return not allowed_domains or any(hostname.endswith(domain.lower()) for domain in allowed_domains)


def screen_sources(source_urls: list[str], max_links: int, config: PipelineConfig) -> list[CandidateRecord]:
    queued: list[CandidateRecord] = []

    for source_url in source_urls:
        upsert_source_page(source_url, config.sourceDiscovery.revisitFrequencyDays)
        page = fetch_page(source_url)
        for link in page.links:
            if len(queued) >= max_links:
                break
            if not is_allowed_url(link, config.sourceDiscovery.allowedDomains, config.sourceDiscovery.blockedDomains):
                continue
            queued.append(enqueue_candidate(link, discovered_from=source_url))
        mark_source_visited(source_url, config.sourceDiscovery.revisitFrequencyDays)

    return queued
