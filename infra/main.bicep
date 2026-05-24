targetScope = 'resourceGroup'

@description('Environment name used as a suffix for resource names.')
param environmentName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Create an Azure AI Services resource for Microsoft Foundry / Azure OpenAI compatible model deployments.')
param createAzureAI bool = true

@description('Azure OpenAI / Foundry chat model deployment name for structured extraction. Leave empty only while provisioning resources before model setup.')
param azureOpenAIDeployment string = ''

@description('Azure OpenAI embedding deployment name used for embedding-based duplicate detection. Leave empty only while provisioning resources before model setup.')
param azureOpenAIEmbeddingDeployment string = ''

@description('Azure OpenAI / Foundry model deployment name used for groundedness checks. Leave empty only while provisioning resources before model setup.')
param azureOpenAIGroundednessDeployment string = ''

@description('Optional Microsoft Foundry project endpoint used by Microsoft Agent Framework chat calls. Example: https://<account>.services.ai.azure.com/api/projects/<project>.')
param azureAIProjectEndpoint string = ''

@description('Embedding dimensions for the Records container vector policy. Match the configured embedding model deployment.')
@minValue(1)
param embeddingDimensions int = 3072

var normalizedName = toLower(replace(environmentName, '-', ''))
var unique = uniqueString(resourceGroup().id, environmentName)
var storageName = take('st${normalizedName}${unique}', 24)
var appInsightsName = 'appi-${environmentName}'
var workspaceName = 'log-${environmentName}'
var cosmosName = 'cosmos-${environmentName}-${take(unique, 6)}'
var aiServicesName = take('ai-${environmentName}-${take(unique, 6)}', 64)
var planName = 'plan-${environmentName}'
var functionName = 'func-${environmentName}-${take(unique, 6)}'
var databaseName = 'explorative-pipeline'
var baseFunctionAppSettings = [
  { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${storageName};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storage.listKeys().keys[0].value}' }
  { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'COSMOS_DATABASE_NAME', value: databaseName }
  { name: 'CosmosDBConnection', value: cosmos.listConnectionStrings().connectionStrings[0].connectionString }
  { name: 'PIPELINE_CONFIG_PATH', value: 'pipeline.config.json' }
  { name: 'SOURCE_REFRESH_CRON', value: '0 0 3 * * *' }
  { name: 'MAX_LINKS_PER_SOURCE', value: '25' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: createAzureAI ? aiServices!.properties.endpoint : '' }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAIDeployment }
  { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAIEmbeddingDeployment }
  { name: 'AZURE_OPENAI_GROUNDEDNESS_DEPLOYMENT', value: azureOpenAIGroundednessDeployment }
]
var functionAppSettings = concat(
  baseFunctionAppSettings,
  empty(azureAIProjectEndpoint) ? [] : [
    { name: 'AZURE_AI_PROJECT_ENDPOINT', value: azureAIProjectEndpoint }
  ]
)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource packageContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'app-package'
  properties: {
    publicAccess: 'None'
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      {
        name: 'EnableNoSQLVectorSearch'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
  }
}

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = if (createAzureAI) {
  name: aiServicesName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: aiServicesName
    publicNetworkAccess: 'Enabled'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

var containers = [
  { name: 'PipelineConfig', pk: '/PartitionKey' }
  { name: 'SourcePageRegistry', pk: '/pk' }
  { name: 'CandidateQueue', pk: '/PartitionKey' }
  { name: 'ReviewQueue', pk: '/PartitionKey' }
  { name: 'PipelineRuns', pk: '/PartitionKey' }
  { name: 'TokenUsage', pk: '/agentName' }
]

resource sqlContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for item in containers: {
  parent: database
  name: item.name
  properties: {
    resource: {
      id: item.name
      partitionKey: {
        paths: [item.pk]
        kind: 'Hash'
      }
    }
  }
}]

resource recordsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Records'
  properties: {
    resource: any({
      id: 'Records'
      partitionKey: {
        paths: ['/PartitionKey']
        kind: 'Hash'
      }
      vectorEmbeddingPolicy: {
        vectorEmbeddings: [
          {
            path: '/embedding'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: embeddingDimensions
          }
        ]
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
          {
            path: '/embedding/*'
          }
        ]
        vectorIndexes: [
          {
            path: '/embedding'
            type: 'quantizedFlat'
          }
        ]
      }
    })
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionName
  location: location
  kind: 'functionapp,linux'
  dependsOn: [
    packageContainer
  ]
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      runtime: {
        name: 'python'
        version: '3.11'
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 20
        instanceMemoryMB: 2048
      }
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}app-package'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'AzureWebJobsStorage'
          }
        }
      }
    }
    siteConfig: {
      appSettings: functionAppSettings
    }
  }
}

output AZURE_FUNCTION_NAME string = functionApp.name
output AZURE_FUNCTION_URI string = 'https://${functionApp.properties.defaultHostName}'
output COSMOS_ACCOUNT_NAME string = cosmos.name
output AZURE_AI_SERVICES_NAME string = createAzureAI ? aiServices!.name : ''
output AZURE_AI_SERVICES_ENDPOINT string = createAzureAI ? aiServices!.properties.endpoint : ''
