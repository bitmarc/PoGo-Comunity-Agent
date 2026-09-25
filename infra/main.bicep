// Infraestructura de HXQ Agent en Azure Container Apps.
//
// Lo que NO crea a proposito:
//  - El recurso de Azure OpenAI: ya existe (hxq-agent-oai) y no se toca desde aqui.
//  - La base de datos: es Neon, fuera de Azure, y llega como secreto.
//  - Container Registry: se usa GHCR, que es gratis. ACR Basic son ~$5/mes fijos.
//
// Desplegar:
//   az deployment group create -g <rg> -f infra/main.bicep -p @infra/main.parameters.json

@description('Prefijo de los recursos. Corto: algunos nombres tienen limite de longitud.')
param prefijo string = 'hxq'

@description('Region. Conviene que coincida con la del recurso de Azure OpenAI.')
param ubicacion string = resourceGroup().location

@description('Imagen del contenedor, en GHCR.')
param imagen string

@description('Nombre del recurso de Azure OpenAI existente al que se dara acceso.')
param nombreAzureOpenAI string

@description('Cliente OAuth de Google.')
param googleClientId string

@secure()
@description('Secreto del cliente OAuth de Google.')
param googleClientSecret string

@secure()
@description('Secreto de firma de sesion de Chainlit. Generar con: openssl rand -hex 32')
param chainlitAuthSecret string

@secure()
@description('Cadena de conexion de Neon Postgres.')
param databaseUrl string

@secure()
@description('Key de Tavily para la busqueda web.')
param tavilyApiKey string

@description('Correos con acceso, separados por coma.')
param adminEmails string

@description('Usuario de GitHub dueno del paquete en GHCR.')
param ghcrUsuario string

@secure()
@description('Token con read:packages para bajar la imagen de GHCR. El paquete es privado porque el repo lo es; sin esto la Container App no puede hacer pull.')
param ghcrToken string

@description('Deployment del modelo de chat en el recurso de Azure OpenAI.')
param chatDeployment string = 'gpt-5.6-luna'

@description('Deployment del modelo de imagen. Verificar el nombre real con: az cognitiveservices account deployment list -n <recurso> -g <rg> -o table')
param imageDeployment string = 'gpt-image-2'

@description('Replicas minimas. 0 = escala a cero (cold start ~15s). 1 = sin cold start.')
@minValue(0)
@maxValue(1)
param replicasMinimas int = 0

var sufijo = uniqueString(resourceGroup().id)
var nombreStorage = toLower('${prefijo}st${sufijo}')
var nombreContenedorBlob = 'hxq-media'

// ---------------------------------------------------------------------------
// Identidad
// ---------------------------------------------------------------------------
// Asignada por el usuario, no del sistema: asi los role assignments sobreviven a
// recrear la Container App y no hay que volver a concederlos.
resource identidad 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefijo}-identity'
  location: ubicacion
}

// ---------------------------------------------------------------------------
// Observabilidad
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefijo}-logs'
  location: ubicacion
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefijo}-insights'
  location: ubicacion
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ---------------------------------------------------------------------------
// Almacenamiento de imagenes y adjuntos
// ---------------------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: nombreStorage
  location: ubicacion
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    // Nada publico: se accede solo con SAS firmado por la identidad.
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource contenedorBlob 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: nombreContenedorBlob
  properties: {
    publicAccess: 'None'
  }
}

// ---------------------------------------------------------------------------
// Permisos
// ---------------------------------------------------------------------------
// GUIDs de roles integrados. Verificar con:
//   az role definition list --name "Storage Blob Data Contributor" --query "[].name" -o tsv
var rolBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var rolBlobDelegator = 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a'
var rolOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource permisoBlobEscritura 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identidad.id, rolBlobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolBlobDataContributor)
    principalId: identidad.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Imprescindible y facil de olvidar: sin Blob Delegator no se puede pedir la user
// delegation key, y sin ella no se firman URLs de lectura sin la clave de cuenta.
resource permisoBlobDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identidad.id, rolBlobDelegator)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolBlobDelegator)
    principalId: identidad.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource azureOpenAI 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: nombreAzureOpenAI
}

resource permisoOpenAI 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: azureOpenAI
  name: guid(azureOpenAI.id, identidad.id, rolOpenAIUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolOpenAIUser)
    principalId: identidad.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Container Apps
// ---------------------------------------------------------------------------
resource entorno 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefijo}-env'
  location: ubicacion
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefijo}-agent'
  location: ubicacion
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identidad.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: entorno.id
    configuration: {
      // Obligatorio y explicito: la afinidad de sesion solo se admite en modo Single.
      // Sin declararlo, la API rechaza el despliegue con
      // ContainerAppInvalidIngressStickySessionRevisionMode.
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        // 'auto' deja pasar el upgrade a WebSocket, que Chainlit necesita.
        transport: 'auto'
        // Chainlit mantiene estado de sesion en memoria: sin afinidad, otra replica
        // recibiria mensajes de una conversacion que no conoce.
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: 'ghcr.io'
          username: ghcrUsuario
          passwordSecretRef: 'ghcr-token'
        }
      ]
      secrets: [
        {
          name: 'ghcr-token'
          value: ghcrToken
        }
        {
          name: 'google-client-secret'
          value: googleClientSecret
        }
        {
          name: 'chainlit-auth-secret'
          value: chainlitAuthSecret
        }
        {
          name: 'database-url'
          value: databaseUrl
        }
        {
          name: 'tavily-api-key'
          value: tavilyApiKey
        }
        {
          name: 'appinsights-connection'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'hxq-agent'
          image: imagen
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            // Azure OpenAI sin API key: la identidad tiene el rol y
            // DefaultAzureCredential la elige por AZURE_CLIENT_ID.
            {
              name: 'AZURE_CLIENT_ID'
              value: identidad.properties.clientId
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAI.properties.endpoint
            }
            {
              name: 'HXQ_CHAT_DEPLOYMENT'
              value: chatDeployment
            }
            {
              name: 'HXQ_IMAGE_DEPLOYMENT'
              value: imageDeployment
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT'
              value: storage.name
            }
            {
              name: 'AZURE_STORAGE_CONTAINER'
              value: nombreContenedorBlob
            }
            {
              name: 'HXQ_ADMIN_EMAILS'
              value: adminEmails
            }
            {
              name: 'OAUTH_GOOGLE_CLIENT_ID'
              value: googleClientId
            }
            {
              name: 'OAUTH_GOOGLE_CLIENT_SECRET'
              secretRef: 'google-client-secret'
            }
            {
              name: 'CHAINLIT_AUTH_SECRET'
              secretRef: 'chainlit-auth-secret'
            }
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'TAVILY_API_KEY'
              secretRef: 'tavily-api-key'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection'
            }
          ]
          probes: [
            {
              type: 'Readiness'
              httpGet: {
                path: '/'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: replicasMinimas
        // Tope de 1: Chainlit guarda estado de sesion en memoria. Escalar mas exige
        // moverlo fuera del proceso, y para unos pocos admins no hace falta.
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    permisoOpenAI
    permisoBlobEscritura
    permisoBlobDelegator
  ]
}

output urlApp string = 'https://${app.properties.configuration.ingress.fqdn}'
output redirectUriGoogle string = 'https://${app.properties.configuration.ingress.fqdn}/auth/oauth/google/callback'
output cuentaStorage string = storage.name
output identidadClientId string = identidad.properties.clientId
