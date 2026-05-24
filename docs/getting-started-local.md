# Getting Started: Local Testing

This guide walks through setting up the project locally, running tests, starting the Azure Functions host, and calling the HTTP endpoints.

## 1. Prerequisites

Install these tools first:

- Python 3.11, matching the deployed Azure Functions runtime.
- Azure Functions Core Tools v4.
- Azurite or an Azure Storage account for `AzureWebJobsStorage`.
- A Cosmos DB for NoSQL account or local Cosmos DB emulator for pipeline state.
- Azure AI Services / Azure OpenAI model deployments for extraction, embeddings, and groundedness.

For a quick code-only check, you only need Python and the package dependencies. For full local pipeline testing, configure Storage, Cosmos DB, and model settings in `local.settings.json`.

## 2. Clone And Create A Virtual Environment

```powershell
git clone https://github.com/flo7up/ai-web-scraping-pipeline.git
cd ai-web-scraping-pipeline
py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

If `py -3.11` is not available, install Python 3.11 or use your local Python executable explicitly.

## 3. Run The Test Suite

```powershell
./.venv/Scripts/python.exe -m pytest
```

This validates configuration parsing, extraction helpers, review logic, prompt rendering, groundedness helpers, and duplicate detection.

You can also check that the Functions app imports and registers its blueprints:

```powershell
./.venv/Scripts/python.exe -c "import function_app; print('function_app import ok')"
```

## 4. Configure Local Settings

Create a local settings file:

```powershell
Copy-Item local.settings.sample.json local.settings.json
```

Edit `local.settings.json` and fill in these values:

```json
{
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "PIPELINE_CONFIG_PATH": "pipeline.config.json",
    "CosmosDBConnection": "<cosmos-db-connection-string>",
    "COSMOS_DATABASE_NAME": "explorative-pipeline",
    "AZURE_OPENAI_ENDPOINT": "https://<your-ai-service>.cognitiveservices.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "<chat-model-deployment>",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "<embedding-model-deployment>",
    "AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT": "<groundedness-model-deployment>",
    "AZURE_OPENAI_API_KEY": "<local-dev-api-key>",
    "GOOGLE_SEARCH_API_KEY": "<google-custom-search-api-key>",
    "GOOGLE_SEARCH_ENGINE_ID": "<google-programmable-search-engine-id>"
  }
}
```

Notes:

- Keep `local.settings.json` out of git. It is already ignored.
- For local development, an API key is usually the simplest Azure OpenAI auth path.
- For production, prefer managed identity and role-based access where available.
- `AzureWebJobsStorage=UseDevelopmentStorage=true` expects Azurite to be running.

Start Azurite in a separate terminal if you use local development storage:

```powershell
azurite
```

## 5. Configure The Pipeline Domain

Edit `pipeline.config.json`:

- `domainDescription`: describe what you want to discover.
- `sourceDiscovery.seedUrls`: add starting pages.
- `sourceDiscovery.searchProvider`: set to `yandex` for a low-volume search-based smoke test.
- `sourceDiscovery.searchQueries`: add search queries such as `site:example.com Example Domain`.
- `sourceDiscovery.allowedDomains`: add a domain allow-list for safer early tests.
- `sourceDiscovery.maxLinksPerSource`: keep this low, such as `3` to `5`, for the first run.
- `schema.fields`: define the structured fields you expect.
- `prompts`: point to prompt files under `prompts/`.

For a first local run, use one or two seed pages and a small link cap. This prevents accidental large crawls and keeps model costs predictable. For reliable search-based discovery, set `sourceDiscovery.searchProvider` to `google` and configure `GOOGLE_SEARCH_API_KEY` plus `GOOGLE_SEARCH_ENGINE_ID`. Yandex can be useful for small demos, but it may return captcha challenges instead of usable results.

## 6. Customize Prompts

Prompt templates live in `prompts/`:

- `prompts/extraction.system.md`
- `prompts/extraction.user.md`
- `prompts/groundedness.system.md`
- `prompts/groundedness.user.md`

The extraction prompt can use placeholders such as:

- `{{domainDescription}}`
- `{{recordType}}`
- `{{schemaJson}}`
- `{{sourceUrl}}`
- `{{sourceTitle}}`
- `{{sourceText}}`

The groundedness prompt can use:

- `{{groundednessThreshold}}`
- `{{sourceText}}`
- `{{recordClaims}}`

Keep prompts source-grounded. Ask the model to extract only facts that appear in the source text.

## 7. Start The Functions Host

```powershell
func start
```

The host should discover the HTTP endpoints, Cosmos DB triggers, and timer trigger from `function_app.py`.

Expected HTTP routes include:

- `POST http://localhost:7071/api/extract-url`
- `POST http://localhost:7071/api/screen-sources`
- `GET http://localhost:7071/api/records`

## 8. Test A Single URL Extraction

This is the smallest useful local endpoint test because it fetches a page and runs structured extraction without writing queue documents.

```powershell
$body = @{ url = "https://example.com" } | ConvertTo-Json
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:7071/api/extract-url" `
  -ContentType "application/json" `
  -Body $body
```

Replace `https://example.com` with a real public page from your target domain.

## 9. Test Source Screening

This endpoint reads seed pages, extracts links, filters them, and writes candidates into the `CandidateQueue` Cosmos DB container.

```powershell
$body = @{
  urls = @("https://example.com")
  maxLinks = 3
} | ConvertTo-Json

Invoke-RestMethod -Method POST `
  -Uri "http://localhost:7071/api/screen-sources" `
  -ContentType "application/json" `
  -Body $body
```

To test Google-based discovery without changing `pipeline.config.json`, pass query overrides in the request body after setting `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID`:

```powershell
$body = @{
  searchProvider = "google"
  queries = @("site:example.com Example Domain")
  maxLinks = 1
} | ConvertTo-Json

Invoke-RestMethod -Method POST `
  -Uri "http://localhost:7071/api/screen-sources" `
  -ContentType "application/json" `
  -Body $body
```

To test Yandex-based discovery for a low-volume demo, pass query overrides in the request body:

```powershell
$body = @{
  searchProvider = "yandex"
  queries = @("site:example.com Example Domain")
  maxLinks = 1
} | ConvertTo-Json

Invoke-RestMethod -Method POST `
  -Uri "http://localhost:7071/api/screen-sources" `
  -ContentType "application/json" `
  -Body $body
```

Google Custom Search is recommended for repeatable discovery. Yandex search is best for small smoke tests and may return `blocked_or_challenged` diagnostics if it serves a captcha page. For repeatable production runs, prefer Google Custom Search or curated `seedUrls` and domain allow-lists.

After this succeeds, check the `CandidateQueue` container in Cosmos DB. The candidate trigger should process queued candidates when the Functions host is running and the Cosmos DB trigger connection is valid.

## 10. Search Approved Records

After review items are approved and stored, query records locally:

```powershell
Invoke-RestMethod -Method GET "http://localhost:7071/api/records?limit=10"
```

Use `q` to search title and summary text:

```powershell
Invoke-RestMethod -Method GET "http://localhost:7071/api/records?q=automation&limit=10"
```

## 11. Local Troubleshooting

### `func start` cannot find Python or the wrong Python version

Use Python 3.11 for the closest match to Azure Functions:

```powershell
py -0p
py -3.11 --version
```

Recreate the virtual environment if needed.

### `AzureWebJobsStorage` fails

Start Azurite or replace `UseDevelopmentStorage=true` with a real Azure Storage connection string.

### Cosmos DB trigger does not run

Check:

- `CosmosDBConnection` is set in `local.settings.json`.
- `COSMOS_DATABASE_NAME` matches the database.
- Containers exist or were provisioned by the Azure deployment.
- The Functions host logs show the Cosmos DB trigger listeners starting.

### Model calls fail

Check:

- `AZURE_OPENAI_ENDPOINT` points to the Azure AI Services endpoint.
- `AZURE_OPENAI_DEPLOYMENT` is a chat model deployment name.
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` is an embedding model deployment name.
- `AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT` is set for groundedness review.
- `AZURE_OPENAI_API_KEY` is present for local key-based auth, or your local identity has access.

### Costs rise unexpectedly

Start with:

- one seed URL
- `maxLinksPerSource` between `3` and `5`
- conservative `llm.maxInputChars`, `embedding.maxInputChars`, and `groundedness.maxInputChars`

Then increase cadence and source volume only after reviewing Application Insights and Azure AI token usage.
