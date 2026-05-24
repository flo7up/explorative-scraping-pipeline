import json

import azure.functions as func
from src.functions import http_search_records


def _request(params: dict[str, str]) -> func.HttpRequest:
    return func.HttpRequest(method="GET", url="/api/records", params=params, body=b"")


def test_parse_limit_rejects_invalid_values():
    response = http_search_records.http_search_records(_request({"limit": "abc"}))
    assert response.status_code == 400
    assert json.loads(response.get_body())["error"] == "limit must be an integer"


def test_records_excludes_embedding_by_default(monkeypatch):
    captured = {}

    def fake_query(alias, query_text, parameters=None, **kwargs):
        captured["query"] = query_text
        return [{"id": "1", "title": "A title"}]

    monkeypatch.setattr(http_search_records.cosmos, "query", fake_query)
    response = http_search_records.http_search_records(_request({}))

    assert response.status_code == 200
    assert "c.embedding," not in captured["query"]
    assert "c.embedding FROM" not in captured["query"]
    assert json.loads(response.get_body())["count"] == 1


def test_records_can_include_embedding_when_requested(monkeypatch):
    captured = {}

    def fake_query(alias, query_text, parameters=None, **kwargs):
        captured["query"] = query_text
        return [{"id": "1", "title": "A title", "embedding": [0.1]}]

    monkeypatch.setattr(http_search_records.cosmos, "query", fake_query)
    response = http_search_records.http_search_records(_request({"includeEmbedding": "true"}))

    assert response.status_code == 200
    assert "c.embedding" in captured["query"]
    assert json.loads(response.get_body())["items"][0]["embedding"] == [0.1]