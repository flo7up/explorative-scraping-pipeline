import logging
from typing import Any

from src.pipeline import cosmos
from src.pipeline.config import PipelineConfig
from src.pipeline.deduplication import apply_source_identity_fields, find_duplicate_record
from src.pipeline.embeddings import apply_embedding_fields, create_record_embedding
from src.pipeline.groundedness import evaluate_groundedness
from src.pipeline.http_client import fetch_page
from src.pipeline.models import ExtractedRecord
from src.pipeline.review import review_record

logger = logging.getLogger(__name__)


def fetch_source_text(source_url: str) -> str:
    try:
        return fetch_page(source_url).text
    except Exception as exc:
        logger.warning("Groundedness source fetch failed for %s: %s: %s", source_url, type(exc).__name__, exc)
        return ""


def review_item(item: dict[str, Any], config: PipelineConfig) -> dict[str, Any]:
    if item.get("status") not in {"queued", None}:
        return item

    try:
        record = ExtractedRecord.model_validate(item["record"])
        approved, reasons = review_record(record, config)
        record_data = apply_source_identity_fields(record.model_dump())

        embedding = create_record_embedding(record, config)
        record_data = apply_embedding_fields(record_data, embedding, config)

        duplicate_review = None
        if approved:
            duplicate_review = find_duplicate_record(record_data, config, embedding=embedding)
            if duplicate_review:
                approved = False
                reasons.append(f"Duplicate record: {duplicate_review['reason']}")

        groundedness = None
        if approved:
            source_text = fetch_source_text(record.sourceUrl)
            groundedness = evaluate_groundedness(record_data, source_text, config)
            record_data["groundedness"] = groundedness
            if config.groundedness.requirePass and groundedness.get("passed") is False:
                approved = False
                reasons.append(f"Groundedness check failed: {groundedness.get('reason')}")

        item["duplicateReview"] = duplicate_review or {"status": "unique" if approved else "not_checked"}
        if groundedness:
            item["groundedness"] = groundedness
        item["reasons"] = reasons
        item["status"] = "approved" if approved else "rejected"
        if approved:
            cosmos.upsert("records", {**record_data, "status": "approved"})
    except Exception as exc:
        item["status"] = "failed"
        item["reasons"] = [str(exc)]
        raise
    finally:
        cosmos.upsert("review", item)

    return item
