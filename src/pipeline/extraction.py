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


def llm_extract(url: str, title: str, text: str, config: PipelineConfig) -> ExtractedRecord | None:
    deployment = os.getenv(config.llm.deploymentNameEnv)
    if not deployment:
        return None

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
        return None
    data.setdefault("sourceUrl", url)
    data.setdefault("recordType", config.recordType)
    data.setdefault("title", title or data.get("summary") or "Untitled record")
    data.setdefault("summary", _first_sentence(text))
    data.setdefault("rawFields", {})
    data["rawFields"]["extractionMode"] = "llm"
    return ExtractedRecord.model_validate(data)


def extract_record(url: str, title: str, text: str, config: PipelineConfig) -> ExtractedRecord:
    return llm_extract(url, title, text, config) or deterministic_extract(url, title, text, config)
