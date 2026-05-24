import logging
import os
import re
from typing import Any

from .config import PipelineConfig
from .llm import chat_json
from .models import ExtractedRecord
from .prompt_templates import render_prompt_file

logger = logging.getLogger(__name__)

STOPWORDS = {
    "about",
    "after",
    "also",
    "from",
    "have",
    "into",
    "more",
    "that",
    "their",
    "there",
    "these",
    "this",
    "uses",
    "were",
    "with",
    "would",
}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9+#.]+", " ", text)
    return " ".join(text.split())


def meaningful_tokens(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) > 3 and token not in STOPWORDS}


def build_claim_text(record: ExtractedRecord | dict[str, Any]) -> str:
    payload = record.model_dump() if isinstance(record, ExtractedRecord) else record
    parts = [
        payload.get("title"),
        payload.get("summary"),
        payload.get("organization"),
        payload.get("useCaseType"),
        payload.get("industry"),
        " ".join(payload.get("technologies") or []),
    ]
    raw_fields = payload.get("rawFields") or {}
    if isinstance(raw_fields, dict):
        parts.extend(str(value) for value in raw_fields.values() if not isinstance(value, (dict, list)))
    return "\n".join(str(part) for part in parts if part)


def deterministic_groundedness(record: ExtractedRecord | dict[str, Any], source_text: str, config: PipelineConfig) -> dict[str, Any]:
    claim_tokens = meaningful_tokens(build_claim_text(record))
    source_tokens = meaningful_tokens(source_text)
    if not claim_tokens or not source_tokens:
        overlap_ratio = 0.0
    else:
        overlap_ratio = len(claim_tokens.intersection(source_tokens)) / max(len(claim_tokens), 1)

    if overlap_ratio >= 0.75:
        score = 5.0
    elif overlap_ratio >= 0.55:
        score = 4.0
    elif overlap_ratio >= 0.35:
        score = 3.0
    elif overlap_ratio >= 0.2:
        score = 2.0
    else:
        score = 1.0

    passed = score >= config.groundedness.threshold
    return {
        "score": score,
        "result": "pass" if passed else "fail",
        "reason": f"Deterministic token overlap with source text was {overlap_ratio:.2f}.",
        "threshold": config.groundedness.threshold,
        "passed": passed,
        "mode": "deterministic",
    }


def llm_groundedness(record: ExtractedRecord | dict[str, Any], source_text: str, config: PipelineConfig) -> dict[str, Any] | None:
    deployment = os.getenv(config.groundedness.deploymentNameEnv)
    if not deployment:
        return None

    prompt_values = {
        "groundednessThreshold": config.groundedness.threshold,
        "sourceText": source_text[: config.groundedness.maxInputChars],
        "recordClaims": build_claim_text(record),
    }
    system_prompt = render_prompt_file(config.prompts.groundednessSystem, prompt_values)
    user_prompt = render_prompt_file(config.prompts.groundednessUser, prompt_values)

    try:
        result = chat_json(system_prompt, user_prompt, deployment=deployment, temperature=0)
    except Exception as exc:
        logger.warning("LLM groundedness check failed: %s: %s", type(exc).__name__, exc)
        return None

    if not result:
        return None

    score = result.get("score") or result.get("groundedness") or result.get("groundedness_score")
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0
    threshold = float(result.get("threshold") or config.groundedness.threshold)
    passed = bool(result.get("passed")) if "passed" in result else numeric_score >= threshold
    return {
        "score": numeric_score,
        "result": str(result.get("result") or ("pass" if passed else "fail")).lower(),
        "reason": result.get("reason") or result.get("groundedness_reason") or "No reason returned.",
        "threshold": threshold,
        "passed": passed,
        "mode": "llm",
    }


def evaluate_groundedness(record: ExtractedRecord | dict[str, Any], source_text: str | None, config: PipelineConfig) -> dict[str, Any]:
    if not config.groundedness.enabled:
        return {
            "score": None,
            "result": "skipped",
            "reason": "Groundedness check is disabled.",
            "threshold": config.groundedness.threshold,
            "passed": None,
            "mode": "disabled",
        }

    if not source_text:
        return {
            "score": None,
            "result": "skipped",
            "reason": "No source text was available for groundedness evaluation.",
            "threshold": config.groundedness.threshold,
            "passed": None,
            "mode": "missing_context",
        }

    return llm_groundedness(record, source_text, config) or deterministic_groundedness(record, source_text, config)