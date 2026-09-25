# Superficie de API verificada

Comprobado por introspeccion contra lo que quedo instalado, no contra documentacion.
Fecha: 2026-09-23. Versiones: `agent-framework-core` 1.19.0, `agent-framework-foundry`
1.13.1, `agent-framework-openai` 1.14.4, `chainlit` 2.12.0, Python 3.13.13.

## Correcciones respecto al plan original

El plan asumia la API de Semantic Kernel / MAF temprano. La real es distinta:

| Se asumia | Es en realidad |
|---|---|
| `ChatAgent(chat_client=...)` | `Agent(client, instructions, *, name, tools, ...)` |
| `agent_framework.azure.AzureOpenAIChatClient` | **no existe**; `agent_framework.openai.OpenAIChatClient(azure_endpoint=...)` |
| `AgentThread` / `agent.get_new_thread()` | `AgentSession` / `agent.create_session()` |
| `agent.run_stream(...)` | `agent.run(..., stream=True)` -> `ResponseStream` |
| `setup_observability()` | `agent_framework.observability.configure_otel_providers()` / `enable_instrumentation()` |

## Lo que si se confirmo del plan

- `HandoffBuilder(participants=[...]).with_start_agent(x).add_handoff(a, [b, c]).build()`
  existe en `agent_framework.orchestrations`, junto con `SequentialBuilder`,
  `ConcurrentBuilder`, `GroupChatBuilder` y `MagenticBuilder`. La Fase 5 es viable tal cual.
- `ResponsesHostServer` existe en `agent_framework.foundry` (hosting de agentes).
- El provider de Google de Chainlit usa exactamente `OAUTH_GOOGLE_CLIENT_ID` y
  `OAUTH_GOOGLE_CLIENT_SECRET`.

## Detalles que cuestan una tarde si no se saben

1. **El system prompt NO viaja como mensaje.** `Agent` lo pasa en
   `options["instructions"]` al cliente. Buscarlo en la lista de `messages` no lo encuentra.
2. **`FoundryChatClient` no acepta API key.** Solo credenciales de Entra
   (`project_endpoint` + `credential`). Para un recurso de Azure OpenAI normal, el cliente
   correcto es `OpenAIChatClient`, que acepta `azure_endpoint` + (`api_key` | `credential`).
3. **`agent-framework-core` usa imports perezosos.** `agent_framework.foundry.FoundryChatClient`
   lanza `ModuleNotFoundError` pidiendo `agent-framework-foundry` hasta que se instala.
   Los sub-paquetes versionan por separado del core (core 1.19.0, foundry 1.13.1).
4. **`@cl.oauth_callback` revienta en import-time** si no hay variables de proveedor
   configuradas. Por eso la logica de acceso vive en `hxq_agent/access.py`, sin Chainlit,
   y `auth.py` solo hace el binding.
5. **`.chainlit/config.toml` necesita `[meta] generated_by`.** Sin esa seccion, Chainlit
   rechaza el archivo como "outdated" y no arranca.
6. **`zoneinfo` necesita el paquete `tzdata`** en Windows y en imagenes slim de Linux.
   Sin el, `ZoneInfo("America/Mexico_City")` falla.
7. **Contenido de mensajes:** no hay `TextContent`; es `Content.from_text(...)`.
8. **El `api-version` depende de la superficie de API, no del recurso.** `OpenAIChatClient`
   habla con la **Responses API** (`/openai/v1/responses`) y su default es `"preview"`.
   Poner un `AZURE_OPENAI_API_VERSION` fijo en el entorno lo sobreescribe y rompe la llamada
   con `400 BadRequest: API version not supported`. Los defaults de cada cliente:

   | Constante en `agent_framework_openai` | Valor |
   |---|---|
   | `DEFAULT_AZURE_OPENAI_RESPONSES_API_VERSION` | `preview` |
   | `DEFAULT_AZURE_OPENAI_CHAT_COMPLETION_API_VERSION` | `2024-12-01-preview` |
   | `DEFAULT_AZURE_OPENAI_EMBEDDING_API_VERSION` | `2024-10-21` |

   Por eso `AZURE_OPENAI_API_VERSION` va **sin valor** y `build_chat_client` solo la pasa
   si esta configurada a proposito. Un valor unico para todo el proyecto rompe al cliente
   que no coincida.
