from src.pipeline.agents.discovery_agent import (
    SearchProviderBlockedError,
    extract_google_result_urls,
    extract_yandex_result_urls,
    is_allowed_url,
    yandex_search,
)
from src.pipeline.config import PipelineConfig, SourceDiscoveryConfig


def test_extract_yandex_result_urls_skips_internal_links_and_unwraps_redirects():
    html = """
    <a href="/search/?text=test">internal</a>
    <a href="https://yandex.cloud/en/services/smartcaptcha">captcha</a>
    <a href="https://yandex.com/clck/jsredir?url=https%3A%2F%2Fexample.com%2Fcase%23section">result</a>
    <a href="https://example.org/other">other</a>
    <a href="https://example.com/case">duplicate normalized</a>
    """
    results = extract_yandex_result_urls(html, limit=5)
    assert results == ["https://example.com/case", "https://example.org/other"]


def test_allowed_url_respects_allow_and_block_lists():
    config = PipelineConfig(
        sourceDiscovery=SourceDiscoveryConfig(
            allowedDomains=["example.com"],
            blockedDomains=["blocked.example.com"],
        )
    )
    assert is_allowed_url("https://news.example.com/case", config.sourceDiscovery.allowedDomains, config.sourceDiscovery.blockedDomains)
    assert not is_allowed_url("https://blocked.example.com/case", config.sourceDiscovery.allowedDomains, config.sourceDiscovery.blockedDomains)
    assert not is_allowed_url("https://example.org/case", config.sourceDiscovery.allowedDomains, config.sourceDiscovery.blockedDomains)


def test_yandex_search_reports_challenge_pages(monkeypatch):
    class Response:
        url = "https://yandex.eu/search/?text=test"
        text = "<html>smartcaptcha</html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.pipeline.agents.discovery_agent.requests.get", lambda *args, **kwargs: Response())

    try:
        yandex_search("test", limit=1)
    except SearchProviderBlockedError as exc:
        assert exc.status == "blocked_or_challenged"
    else:
        raise AssertionError("Expected Yandex challenge pages to raise SearchProviderBlockedError")


def test_extract_google_result_urls():
    payload = {
        "items": [
            {"link": "https://example.com/a#fragment"},
            {"link": "https://example.com/a"},
            {"link": "not-a-url"},
            {"link": "https://example.org/b"},
        ]
    }
    assert extract_google_result_urls(payload, limit=5) == ["https://example.com/a", "https://example.org/b"]
