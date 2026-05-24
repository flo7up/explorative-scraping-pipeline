from src.pipeline.agents.discovery_agent import (
    SearchProviderBlockedError,
    extract_google_result_urls,
    extract_yandex_result_urls,
    generate_search_queries,
    is_allowed_url,
    normalize_generated_queries,
    screen_sources,
    search_yandex_tool,
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


def test_normalize_generated_queries_deduplicates_and_limits():
    payload = {"queries": [" real estate projects ", "real estate projects", "planning portal"]}
    assert normalize_generated_queries(payload, limit=2) == ["real estate projects", "planning portal"]


def test_generate_search_queries_uses_llm_prompt(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-deployment")
    captured = {}

    def fake_chat_json(system_prompt, user_prompt, **kwargs):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        captured["tools"] = kwargs.get("tools")
        return {"queries": ["site:example.com case studies", "public case studies"]}

    monkeypatch.setattr("src.pipeline.agents.discovery_agent.chat_json", fake_chat_json)

    config = PipelineConfig(recordType="case", domainDescription="Public case studies")
    queries = generate_search_queries(config, ["https://example.com"])

    assert queries == ["site:example.com case studies", "public case studies"]
    assert "Public case studies" in captured["user"]
    assert len(captured["tools"]) == 2


def test_search_yandex_tool_returns_json_string(monkeypatch):
    monkeypatch.setattr("src.pipeline.agents.discovery_agent.yandex_search", lambda query, limit=10: ["https://example.com/case"])
    result = search_yandex_tool("test", limit=1)
    assert result == '{"results": ["https://example.com/case"]}'


def test_screen_sources_generates_queries_when_search_queries_are_empty(monkeypatch):
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "key")
    monkeypatch.setenv("GOOGLE_SEARCH_ENGINE_ID", "cx")

    queued_urls = []

    def fake_google_search(query, config, limit=10, timeout=20):
        assert query == "site:example.com case studies"
        return ["https://example.com/case"]

    def fake_enqueue_candidate(url, discovered_from=None):
        queued_urls.append((url, discovered_from))
        from src.pipeline.models import CandidateRecord

        return CandidateRecord(sourceUrl=url, discoveredFrom=discovered_from)

    monkeypatch.setattr("src.pipeline.agents.discovery_agent.generate_search_queries", lambda config, source_urls=None: ["site:example.com case studies"])
    monkeypatch.setattr("src.pipeline.agents.discovery_agent.google_search", fake_google_search)
    monkeypatch.setattr("src.pipeline.agents.discovery_agent.enqueue_candidate", fake_enqueue_candidate)

    diagnostics = []
    config = PipelineConfig(sourceDiscovery=SourceDiscoveryConfig(searchProvider="google", allowedDomains=["example.com"]))
    queued = screen_sources([], 1, config, search_diagnostics=diagnostics)

    assert len(queued) == 1
    assert queued_urls == [("https://example.com/case", "google:site:example.com case studies")]
    assert diagnostics[0]["status"] == "queries_generated"
