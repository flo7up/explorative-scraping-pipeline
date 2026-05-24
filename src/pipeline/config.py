import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SchemaField(BaseModel):
    name: str
    type: Literal["string", "number", "boolean", "array", "object"] = "string"
    required: bool = False


class SchemaConfig(BaseModel):
    fields: list[SchemaField] = Field(default_factory=list)


class SourceDiscoveryConfig(BaseModel):
    seedUrls: list[str] = Field(default_factory=list)
    searchProvider: Literal["none", "yandex", "google"] = "none"
    searchQueries: list[str] = Field(default_factory=list)
    searchMaxResults: int = 10
    googleApiKeyEnv: str = "GOOGLE_SEARCH_API_KEY"
    googleSearchEngineIdEnv: str = "GOOGLE_SEARCH_ENGINE_ID"
    allowedDomains: list[str] = Field(default_factory=list)
    blockedDomains: list[str] = Field(default_factory=list)
    revisitFrequencyDays: int = 14
    maxLinksPerSource: int = 25


class LlmConfig(BaseModel):
    provider: str = "azure-openai"
    deploymentNameEnv: str = "AZURE_OPENAI_DEPLOYMENT"
    maxInputChars: int = 18000
    temperature: float = 0.1


class EmbeddingConfig(BaseModel):
    enabled: bool = True
    deploymentNameEnv: str = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
    profile: str = "provider-neutral-v1"
    dimensions: int = 3072
    maxInputChars: int = 8000


class GroundednessConfig(BaseModel):
    enabled: bool = True
    deploymentNameEnv: str = "AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT"
    maxInputChars: int = 18000
    threshold: float = 3.0
    requirePass: bool = False


class PromptConfig(BaseModel):
    extractionSystem: str = "prompts/extraction.system.md"
    extractionUser: str = "prompts/extraction.user.md"
    groundednessSystem: str = "prompts/groundedness.system.md"
    groundednessUser: str = "prompts/groundedness.user.md"


class QualityConfig(BaseModel):
    requireSourceEvidence: bool = True
    reviewBeforeStore: bool = True
    duplicateDetection: bool = True
    duplicateSimilarityThreshold: float = 0.85
    duplicateConfidenceThreshold: float = 0.9
    duplicateCandidateLimit: int = 8


class PipelineConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    projectName: str = "ai-web-scraping-pipeline"
    recordType: str = "record"
    domainDescription: str = "Public web records."
    sourceDiscovery: SourceDiscoveryConfig = Field(default_factory=SourceDiscoveryConfig)
    recordSchema: SchemaConfig = Field(default_factory=SchemaConfig, alias="schema")
    llm: LlmConfig = Field(default_factory=LlmConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    groundedness: GroundednessConfig = Field(default_factory=GroundednessConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    allowDeterministicFallbackForSmokeTests: bool = False


@lru_cache(maxsize=1)
def load_config() -> PipelineConfig:
    path = Path(os.getenv("PIPELINE_CONFIG_PATH", "pipeline.config.json"))
    if not path.exists():
        return PipelineConfig()
    return PipelineConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
