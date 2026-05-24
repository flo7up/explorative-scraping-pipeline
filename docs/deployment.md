# Deployment

## Prerequisites

- Azure Developer CLI
- Azure CLI
- Azure Functions Core Tools
- Python 3.11

## Deploy

### Option A: One-click Azure resource deployment

Use the Deploy to Azure button in the README to provision:

- Azure Functions Flex Consumption plan and Function App
- Azure Storage
- Azure Cosmos DB account, database, and containers, including a vector-search-enabled `Records` container
- Azure AI Services resource for Microsoft Foundry / Azure OpenAI-compatible deployments
- Application Insights and Log Analytics

This path provisions resources and app settings. It does not create model deployments or publish Function App code. Configure model deployments before operational runs, and use GitHub Actions or `azd up` when you also want to publish Function App code.

### Option B: Full deployment with Azure Developer CLI

```powershell
azd auth login
azd up
```

This provisions resources and deploys the Python Functions code.

## Configure GitHub OIDC

The included deploy workflow expects repository variables or secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_ENV_NAME`
- `AZURE_LOCATION`

Grant the federated identity permissions to deploy the resources in your target subscription or resource group.

## Microsoft Foundry model setup

The template creates an Azure AI Services resource, but it does not create model deployments. Treat model setup as a required post-deployment step before running the full pipeline.

After deployment:

1. Open the Azure AI Services resource in Microsoft Foundry.
2. Deploy a chat model and set `AZURE_OPENAI_DEPLOYMENT` to the model deployment name.
3. Deploy an embedding model and set `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` for vector duplicate detection.
4. Deploy a groundedness model and set `AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT` for model-based groundedness checks.
5. To use Microsoft Agent Framework for chat-style agent calls, set `AZURE_AI_PROJECT_ENDPOINT` to the Foundry project endpoint.
6. Grant the Function App managed identity permission to create and run Foundry agents on that project.
7. Restart the Function App.

Without these deployment settings, the Azure resources can exist but the pipeline is not ready for useful extraction, embedding-based duplicate review, or groundedness evaluation.

### Microsoft Agent Framework RBAC

When `AZURE_AI_PROJECT_ENDPOINT` is set, the Function App uses its managed identity to create short-lived Foundry agents. The identity needs Foundry project data-plane permissions, including `Microsoft.CognitiveServices/accounts/AIServices/agents/write`.

Some tenants may not have a built-in role that includes the exact agent data actions yet. The following PowerShell creates a tightly scoped custom role for one Foundry project and assigns it to the Function App identity:

```powershell
$subscriptionId = "<subscription-id>"
$functionResourceGroup = "<function-app-resource-group>"
$functionAppName = "<function-app-name>"
$foundryProjectResourceId = "/subscriptions/<subscription-id>/resourceGroups/<foundry-rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project-name>"
$roleName = "AI Foundry Agents Operator"

$principalId = az functionapp identity show `
	--subscription $subscriptionId `
	--resource-group $functionResourceGroup `
	--name $functionAppName `
	--query principalId `
	--output tsv

$role = @{
	Name = $roleName
	IsCustom = $true
	Description = "Scoped access for an Azure Function App to create and run Microsoft Foundry agents."
	Actions = @("Microsoft.CognitiveServices/accounts/projects/read")
	NotActions = @()
	DataActions = @(
		"Microsoft.CognitiveServices/accounts/AIServices/agents/read",
		"Microsoft.CognitiveServices/accounts/AIServices/agents/write",
		"Microsoft.CognitiveServices/accounts/AIServices/agents/delete",
		"Microsoft.CognitiveServices/accounts/AIServices/agents/*"
	)
	NotDataActions = @()
	AssignableScopes = @($foundryProjectResourceId)
}

$path = Join-Path $env:TEMP "ai-foundry-agents-operator.json"
$role | ConvertTo-Json -Depth 10 | Set-Content -Path $path -Encoding utf8
if (az role definition list --name $roleName --query "[0].name" --output tsv) {
	az role definition update --role-definition $path
} else {
	az role definition create --role-definition $path
}

az role assignment create `
	--assignee-object-id $principalId `
	--assignee-principal-type ServicePrincipal `
	--role $roleName `
	--scope $foundryProjectResourceId
```

Role assignment propagation can take several minutes. Restart the Function App after assigning the role so managed identity tokens are refreshed.

## Local Development

Copy `local.settings.sample.json` to `local.settings.json`, fill values, then run:

```powershell
func start
```
