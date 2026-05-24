from typing import Any

from src.pipeline import cosmos
from src.pipeline.config import PipelineConfig
from src.pipeline.extraction import extract_record
from src.pipeline.http_client import fetch_page
from src.pipeline.queueing import enqueue_review


def process_candidate(candidate: dict[str, Any], config: PipelineConfig) -> dict[str, Any]:
    if candidate.get("status") not in {"queued", None}:
        return candidate

    try:
        page = fetch_page(candidate["sourceUrl"])
        record = extract_record(page.final_url, page.title, page.text, config)
        if config.quality.reviewBeforeStore:
            enqueue_review(candidate["id"], record.model_dump())
        else:
            approved = {**record.model_dump(), "status": "approved"}
            cosmos.upsert("records", approved)
        candidate["status"] = "extracted"
    except Exception as exc:
        candidate["status"] = "failed"
        candidate["error"] = str(exc)
        raise
    finally:
        cosmos.upsert("candidates", candidate)

    return candidate
