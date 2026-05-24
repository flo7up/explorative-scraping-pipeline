import logging
import os
import re
from typing import Any

from .config import PipelineConfig
from .llm import azure_openai_client
from .models import ExtractedRecord

logger = logging.getLogger(__name__)

PROVIDER_NEUTRAL_REPLACEMENTS = [
    (r"\bazure\s+openai\b", "managed generative AI service"),
    (r"\bopenai\b", "generative AI"),
    (r"\bmicrosoft\s+copilot(?:\s+studio)?\b", "AI assistant"),
    (r"\bcopilot(?:\s+studio)?\b", "AI assistant"),
    (r"\bmicrosoft\s+fabric\b", "analytics platform"),
    (r"\bdynamics\s+365\b", "business application platform"),
    (r"\bpower\s+platform\b", "low-code automation platform"),
    (r"\bpower\s+bi\b", "business intelligence platform"),
    (r"\bazure\s+(?:ai|machine\s+learning|ml)\b", "managed AI platform"),
    (r"\bazure\s+synapse\b", "analytics platform"),
    (r"\bazure\s+cosmos\s+db\b", "cloud database"),
    (r"\bazure\b", "cloud platform"),
    (r"\bmicrosoft\b", "technology provider"),
    (r"\bamazon\s+bedrock\b", "managed generative AI platform"),
    (r"\bbedrock\b", "managed generative AI platform"),
    (r"\bamazon\s+sagemaker\b", "managed machine learning platform"),
    (r"\bsagemaker\b", "managed machine learning platform"),
    (r"\bamazon\s+web\s+services\b", "cloud platform"),
    (r"\baws\b", "cloud platform"),
    (r"\bamazon\b", "technology provider"),
    (r"\bgoogle\s+cloud\s+vertex\s+ai\b", "managed AI platform"),
    (r"\bvertex\s+ai\b", "managed AI platform"),
    (r"\bgoogle\s+gemini\b", "generative AI model"),
    (r"\bgemini\b", "generative AI model"),
    (r"\bgoogle\s+bigquery\b", "analytics warehouse"),
    (r"\bbigquery\b", "analytics warehouse"),
    (r"\bgoogle\s+kubernetes\s+engine\b", "managed container platform"),
    (r"\bgoogle\s+cloud\b", "cloud platform"),
    (r"\bgcp\b", "cloud platform"),
    (r"\bgoogle\b", "technology provider"),
]


def normalize_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text.strip()


def stringify_value(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, list):
        return "; ".join(text for item in value if (text := stringify_value(item)))
    if isinstance(value, dict):
        parts = []
        for key, nested_value in value.items():
            text = stringify_value(nested_value)
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)
    return str(value)


def neutralize_provider_terms(text: str) -> str:
    neutralized = text
    for pattern, replacement in PROVIDER_NEUTRAL_REPLACEMENTS:
        neutralized = re.sub(pattern, replacement, neutralized, flags=re.IGNORECASE)
    neutralized = re.sub(
        r"\bcloud\s+platform(?:\s+cloud\s+platform\b)+",
        "cloud platform",
        neutralized,
        flags=re.IGNORECASE,
    )
    neutralized = re.sub(
        r"\btechnology\s+provider(?:\s+technology\s+provider\b)+",
        "technology provider",
        neutralized,
        flags=re.IGNORECASE,
    )
    return normalize_text(neutralized)


def neutralize_organization_terms(text: str, organization: str | None) -> str:
    if not organization:
        return text
    neutralized = text
    for term in re.split(r"[;,\n]", organization):
        cleaned = normalize_text(term)
        if len(cleaned) > 2:
            neutralized = re.sub(rf"\b{re.escape(cleaned)}\b", "organization", neutralized, flags=re.IGNORECASE)
    return normalize_text(neutralized)


def build_provider_neutral_embedding_text(record: ExtractedRecord | dict[str, Any], config: PipelineConfig) -> str:
    payload = record.model_dump() if isinstance(record, ExtractedRecord) else record
    organization = stringify_value(payload.get("organization"))
    fields = [
        ("title", "Record title"),
        ("summary", "Summary"),
        ("useCaseType", "Use case type"),
        ("industry", "Industry"),
        ("technologies", "Technologies"),
        ("rawFields", "Additional fields"),
    ]

    parts = []
    for field_name, label in fields:
        text = stringify_value(payload.get(field_name))
        text = neutralize_organization_terms(neutralize_provider_terms(text), organization)
        if text:
            parts.append(f"{label}: {text}")

    return "\n".join(parts)[: config.embedding.maxInputChars]


def create_embedding(content: str, config: PipelineConfig) -> list[float]:
    if not config.embedding.enabled:
        return []

    deployment = os.getenv(config.embedding.deploymentNameEnv)
    if not deployment:
        raise RuntimeError(f"Set {config.embedding.deploymentNameEnv} to an embedding model deployment name before review.")

    client = azure_openai_client()
    if client is None:
        raise RuntimeError("Set AZURE_OPENAI_ENDPOINT before creating embeddings.")

    try:
        response = client.embeddings.create(input=normalize_text(content), model=deployment)
    except Exception as exc:
        logger.warning("Embedding creation failed: %s: %s", type(exc).__name__, exc)
        raise

    if not response.data:
        raise RuntimeError("Embedding model returned no vectors.")
    return list(response.data[0].embedding or [])


def create_record_embedding(record: ExtractedRecord | dict[str, Any], config: PipelineConfig) -> list[float]:
    text = build_provider_neutral_embedding_text(record, config)
    if not text:
        return []
    return create_embedding(text, config)


def apply_embedding_fields(record: dict[str, Any], embedding: list[float], config: PipelineConfig) -> dict[str, Any]:
    record["embedding"] = embedding
    record["embeddingProfile"] = config.embedding.profile
    record["embeddingStatus"] = "ready" if embedding else "missing"
    return record