import os

from .config import PipelineConfig
from .llm import chat_json
from .models import ExtractedRecord
from .prompt_templates import render_prompt_file


def _first_sentence(text: str, max_length: int = 320) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    sentence = text.split(". ")[0].strip()
    return sentence[:max_length]


def deterministic_extract(url: str, title: str, text: str, config: PipelineConfig) -> ExtractedRecord:
    summary = _first_sentence(text) or title or f"Record extracted from {url}"
    return ExtractedRecord(
        recordType=config.recordType,
        title=title or summary[:90] or "Untitled record",
        summary=summary,
        sourceUrl=url,
        rawFields={"extractionMode": "deterministic"},
        confidence=0.35,
    )


def _normalize_confidence(value: object) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    if isinstance(value, str):
        normalized = value.strip().lower()
        labels = {
            "low": 0.25,
            "medium": 0.5,
            "moderate": 0.5,
            "high": 0.85,
        }
        if normalized in labels:
            return labels[normalized]
        try:
            return max(0.0, min(float(normalized), 1.0))
        except ValueError:
            return 0.5
    return 0.5


def llm_extract(url: str, title: str, text: str, config: PipelineConfig) -> ExtractedRecord | None:
    deployment = os.getenv(config.llm.deploymentNameEnv)
    if not deployment:
        if config.allowDeterministicFallbackForSmokeTests:
            return None
        raise RuntimeError(f"Set {config.llm.deploymentNameEnv} to a chat model deployment name before running extraction.")

    prompt_values = {
        "domainDescription": config.domainDescription,
        "recordType": config.recordType,
        "sourceUrl": url,
        "sourceTitle": title,
        "schemaJson": [field.model_dump() for field in config.recordSchema.fields],
        "sourceText": text[: config.llm.maxInputChars],
    }
    system_prompt = render_prompt_file(config.prompts.extractionSystem, prompt_values)
    user_prompt = render_prompt_file(config.prompts.extractionUser, prompt_values)

    data = chat_json(system_prompt, user_prompt, deployment=deployment, temperature=config.llm.temperature)
    if not data:
        if config.allowDeterministicFallbackForSmokeTests:
            return None
        raise RuntimeError("LLM extraction returned no structured JSON payload.")
    if not data.get("sourceUrl"):
        data["sourceUrl"] = url
    if not data.get("recordType"):
        data["recordType"] = config.recordType
    if not data.get("title"):
        data["title"] = title or data.get("summary") or "Untitled record"
    if not data.get("summary"):
        data["summary"] = _first_sentence(text)
    if not isinstance(data.get("technologies"), list):
        data["technologies"] = [str(data["technologies"])] if data.get("technologies") else []
    data["confidence"] = _normalize_confidence(data.get("confidence"))
    if not isinstance(data.get("rawFields"), dict):
        data["rawFields"] = {}
    data["rawFields"]["extractionMode"] = "llm"
    return ExtractedRecord.model_validate(data)


def extract_record(url: str, title: str, text: str, config: PipelineConfig) -> ExtractedRecord:
    record = llm_extract(url, title, text, config)
    if record:
        return record
    if config.allowDeterministicFallbackForSmokeTests:
        return deterministic_extract(url, title, text, config)
    raise RuntimeError("LLM extraction did not produce a record.")
