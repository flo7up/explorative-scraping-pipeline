from src.pipeline import queueing


def test_enqueue_review_is_idempotent_for_candidate(monkeypatch):
    stored = []
    existing = {
        "id": "review-candidate-1",
        "PartitionKey": "review",
        "candidateId": "candidate-1",
        "record": {"title": "Existing"},
        "status": "queued",
        "createdAt": "2026-05-24T00:00:00Z",
        "updatedAt": "2026-05-24T00:00:00Z",
        "reasons": [],
    }

    monkeypatch.setattr(queueing.cosmos, "query", lambda *args, **kwargs: [existing])
    monkeypatch.setattr(queueing.cosmos, "upsert", lambda *args, **kwargs: stored.append(args))

    item = queueing.enqueue_review("candidate-1", {"title": "New"})

    assert item.id == "review-candidate-1"
    assert item.record["title"] == "Existing"
    assert stored == []


def test_enqueue_review_uses_deterministic_id(monkeypatch):
    stored = []

    monkeypatch.setattr(queueing.cosmos, "query", lambda *args, **kwargs: [])
    monkeypatch.setattr(queueing.cosmos, "upsert", lambda alias, item: stored.append((alias, item)) or item)

    item = queueing.enqueue_review("candidate-1", {"title": "New"})

    assert item.id == "review-candidate-1"
    assert stored[0][0] == "review"
    assert stored[0][1]["id"] == "review-candidate-1"