# Configuration

The primary configuration file is `pipeline.config.json`.

## Source Discovery

- `seedUrls`: starting pages for exploration.
- `searchProvider`: optional search provider for discovery. Supported values: `none`, `google`, `yandex`.
- `searchQueries`: search queries to run when `searchProvider` is `google` or `yandex`.
- `searchMaxResults`: maximum search results to inspect per query.
- `googleApiKeyEnv`: environment variable containing the Google Custom Search API key. Default: `GOOGLE_SEARCH_API_KEY`.
- `googleSearchEngineIdEnv`: environment variable containing the Google Programmable Search Engine ID. Default: `GOOGLE_SEARCH_ENGINE_ID`.
- `allowedDomains`: optional domain allow-list.
- `blockedDomains`: domain block-list.
- `revisitFrequencyDays`: when source pages become due again.
- `maxLinksPerSource`: candidate cap per source page.

Google Custom Search is recommended for reliable search-based discovery because it provides a supported API, stable JSON responses, and clearer quota/error behavior. Yandex search support is intended for low-volume test and demo runs only. Search result pages can change, throttle automated requests, or return captcha challenges, so keep `maxLinksPerSource` and `searchMaxResults` small and fall back to explicit `seedUrls` for repeatable production runs.

## Schema

Schema fields describe the target record. Required fields are enforced by the review stage.

## LLM Settings

- `deploymentNameEnv`: app setting that contains the Azure OpenAI deployment name.
- `maxInputChars`: source text truncation to control cost.
- `temperature`: keep low for structured extraction.

`allowDeterministicFallbackForSmokeTests` defaults to `false`. Keep it disabled for operational runs so missing model deployments fail fast instead of silently producing low-quality deterministic records. Enable it only for infrastructure smoke tests that intentionally avoid model calls.

## Prompt Templates

- `prompts.extractionSystem`: system prompt file for structured extraction.
- `prompts.extractionUser`: user prompt file for structured extraction.
- `prompts.groundednessSystem`: system prompt file for groundedness review.
- `prompts.groundednessUser`: user prompt file for groundedness review.

Prompt templates live in `prompts/` by default and use `{{placeholder}}` values. See `docs/prompt-customization.md`.

## Embeddings

- `embedding.enabled`: enables provider-neutral embedding generation.
- `embedding.deploymentNameEnv`: app setting containing the embedding deployment name, default `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`.
- `embedding.profile`: profile marker stored with generated embeddings.
- `embedding.dimensions`: vector dimensions expected by the deployed Cosmos DB vector policy.
- `embedding.maxInputChars`: maximum provider-neutral text sent to the embedding model.

Configure an embedding deployment for the intended duplicate-review path. Exact source URL checks are only a narrow duplicate signal and are not a replacement for the embedding-based review flow.

## Groundedness

- `groundedness.enabled`: enables groundedness metadata on approved records.
- `groundedness.deploymentNameEnv`: app setting containing the groundedness model deployment name, default `AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT`.
- `groundedness.maxInputChars`: maximum source text sent to the groundedness model.
- `groundedness.threshold`: score threshold for pass/fail.
- `groundedness.requirePass`: when true, failed groundedness rejects the review item. The default is false, so the result is stored as metadata.

Configure a groundedness deployment for the intended review path. Do not treat deterministic token overlap as a substitute for model-based groundedness in operational runs.

## Quality Gates

- `quality.requireSourceEvidence`: requires a source URL.
- `quality.reviewBeforeStore`: routes extracted records through `ReviewQueue` before storage.
- `quality.duplicateDetection`: enables exact-source and embedding-based duplicate checks.
- `quality.duplicateSimilarityThreshold`: minimum vector similarity for semantic duplicate evidence.
- `quality.duplicateConfidenceThreshold`: minimum combined duplicate confidence.
- `quality.duplicateCandidateLimit`: maximum duplicate candidates considered.

## Environment Settings

See `.env.example` and `local.settings.sample.json`.

## Examples

The `examples/` directory includes:

- `aiusecasehub.pipeline.config.json`: AIUseCaseHub-style AI use case discovery.
- `sustainability.pipeline.config.json`: sustainability and ESG project discovery.

Copy an example over `pipeline.config.json`, then adjust seed URLs and schema fields.

```powershell
Copy-Item examples/aiusecasehub.pipeline.config.json pipeline.config.json
```
