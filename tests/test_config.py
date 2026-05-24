from pathlib import Path

from src.pipeline.config import PipelineConfig


def test_default_config_has_safe_values():
    config = PipelineConfig()
    assert config.projectName == "ai-web-scraping-pipeline"
    assert config.sourceDiscovery.revisitFrequencyDays >= 1
    assert config.sourceDiscovery.googleApiKeyEnv == "GOOGLE_SEARCH_API_KEY"
    assert config.prompts.extractionSystem == "prompts/extraction.system.md"
    assert config.allowDeterministicFallbackForSmokeTests is False
    assert config.quality.reviewBeforeStore is True


def test_pipeline_config_file_is_valid():
    config_path = Path("pipeline.config.json")
    assert config_path.exists()
    config = PipelineConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    assert config.recordType
    assert config.recordSchema.fields
