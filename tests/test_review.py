from src.pipeline.config import PipelineConfig, SchemaConfig, SchemaField
from src.pipeline.deduplication import (
    build_duplicate_decision,
    calculate_duplicate_signals,
    normalize_source_url,
    source_url_hash,
)
from src.pipeline.embeddings import build_provider_neutral_embedding_text
from src.pipeline.groundedness import deterministic_groundedness, evaluate_groundedness
from src.pipeline.models import ExtractedRecord
from src.pipeline.review import review_record


def test_review_requires_configured_fields():
    config = PipelineConfig(recordSchema=SchemaConfig(fields=[SchemaField(name="title", required=True)]))
    record = ExtractedRecord(recordType="case", title="", summary="summary", sourceUrl="https://example.com")
    approved, reasons = review_record(record, config)
    assert approved is False
    assert "Missing required field: title" in reasons


def test_review_accepts_valid_record():
    config = PipelineConfig(recordSchema=SchemaConfig(fields=[SchemaField(name="title", required=True)]))
    record = ExtractedRecord(recordType="case", title="A title", summary="summary", sourceUrl="https://example.com")
    approved, reasons = review_record(record, config)
    assert approved is True
    assert reasons == []


def test_provider_neutral_embedding_text_removes_provider_and_organization_terms():
    config = PipelineConfig()
    record = ExtractedRecord(
        recordType="use_case",
        title="Contoso uses Azure OpenAI for support automation",
        summary="Microsoft Copilot helps Contoso resolve support cases faster.",
        sourceUrl="https://example.com/case",
        organization="Contoso",
    )
    text = build_provider_neutral_embedding_text(record, config).lower()
    assert "contoso" not in text
    assert "azure openai" not in text
    assert "managed generative ai service" in text
    assert "organization" in text


def test_groundedness_deterministic_scores_supported_claims_as_pass():
    config = PipelineConfig()
    record = ExtractedRecord(
        recordType="use_case",
        title="Support automation",
        summary="Contoso uses automation to process support requests faster.",
        sourceUrl="https://example.com/case",
        organization="Contoso",
    )
    result = deterministic_groundedness(
        record,
        "Contoso uses automation to process support requests faster and improve service operations.",
        config,
    )
    assert result["passed"] is True
    assert result["score"] >= config.groundedness.threshold


def test_duplicate_decision_uses_exact_source_identity():
    config = PipelineConfig()
    record = {
        "id": "new",
        "title": "Example case",
        "summary": "Example summary",
        "sourceUrl": "https://example.com/case?utm_source=newsletter",
    }
    candidate = {
        "id": "existing",
        "title": "Different title",
        "summary": "Different summary",
        "sourceUrlHash": source_url_hash("https://example.com/case"),
    }
    signals = calculate_duplicate_signals(record, candidate)
    decision = build_duplicate_decision({"id": "existing", "duplicateSignals": signals}, config)
    assert normalize_source_url(record["sourceUrl"]) == "https://example.com/case"
    assert decision is not None
    assert decision["matchedRecordId"] == "existing"


def test_groundedness_requires_model_deployment_by_default(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT", raising=False)
    record = ExtractedRecord(recordType="case", title="A title", summary="summary", sourceUrl="https://example.com")

    try:
        evaluate_groundedness(record, "summary", PipelineConfig())
    except RuntimeError as exc:
        assert "AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT" in str(exc)
    else:
        raise AssertionError("Expected missing groundedness deployment to fail by default")
