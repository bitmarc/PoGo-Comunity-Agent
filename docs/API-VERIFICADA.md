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

## Fase 2: persistencia y contenedor

Verificado contra Postgres 17 real y contra la imagen construida, no solo leyendo docs.

9. **El esquema del data layer no viene en el paquete.** Esta en el repo aparte
   `Chainlit/chainlit-datalayer`, en `prisma/migrations/`. Las tablas son PascalCase
   entrecomilladas (`"Thread"`) con columnas camelCase (`"threadId"`), estilo Prisma, y el
   data layer las consulta literalmente: renombrar cualquier cosa lo rompe. El DDL copiado
   y hecho idempotente vive en `infra/db/001_chainlit_schema.sql`.
10. **`ChainlitDataLayer` necesita `asyncpg`**, que no es dependencia de `chainlit`.
11. **Chainlit no mapea `tags` al `ThreadDict`.** La columna se escribe bien en la base
    (comprobado), pero `get_thread()` no la devuelve. Si hace falta leer tags, hay que
    consultarlos directamente.
12. **`create_step` esta envuelto en `@queue_until_user_message()`**, que exige el
    contexto de Chainlit (un websocket activo). Para probarlo fuera de la app se llama a
    `dl.create_step.__wrapped__(dl, ...)`.
13. **El `AzureBlobStorageClient` de Chainlit solo acepta storage key**, no Managed
    Identity. Por eso `storage/blob.py` implementa `BaseStorageClient` (4 metodos) con
    `DefaultAzureCredential` y firma las URLs de lectura con una user delegation key.
    Eso exige el rol **Storage Blob Delegator** ademas de Blob Data Contributor: sin el,
    `get_user_delegation_key()` falla y no se pueden generar URLs.
14. **Chainlit escribe en `/app` al arrancar** (`.files` y `.chainlit/translations`). Con
    un usuario sin privilegios el contenedor muere con
    `PermissionError: '/app/.files'`. Hay que crear esos directorios en el Dockerfile con
    el dueno correcto.
15. **Dos trampas del contexto de build**, ambas encontradas construyendo:
    - `*.md` en `.dockerignore` excluye `chainlit.md`, que es la pantalla de bienvenida.
    - Un `COPY public* ./` con `public/` vacio funciona en local pero **falla en CI**:
      git no trackea directorios vacios, asi que en un checkout limpio no existe. De ahi
      el `public/.gitkeep`.

## Fase 2, despliegue: dos cosas que rompen el primer intento

16. **La afinidad de sesion exige `activeRevisionsMode: 'Single'` explicito.** Sin
    declararlo, la API rechaza el despliegue entero con
    `ContainerAppInvalidIngressStickySessionRevisionMode: Sticky Session is not
    supported for  revision mode` (con el hueco donde iria el modo). El resto de los
    recursos si se crea, y reintentar es seguro.
17. **GHCR es privado si el repo lo es.** Sin un bloque `registries` en la Container App,
    el pull falla. Se usa un PAT clasico con unicamente `read:packages` como secreto.
    Comprobado: `docker pull` sin credenciales devuelve `unauthorized`.

Limites practicos de `az containerapp exec`, utiles para depurar en produccion:
- El comando tiene limite de longitud: un `python -c` con base64 de ~2.400 caracteres falla
  con `Handshake status 404`. Scripts cortos funcionan.
- Dentro del `python -c` solo se pueden usar comillas **simples**: las dobles escapadas se
  manglean al pasar por la CLI en Windows.
- Con `minReplicas: 0` hay que despertar la app con una peticion antes del exec, o no hay
  replica a la que conectarse.
- La API tiene rate limit: tras ~6 invocaciones seguidas devuelve `429` con
  `retry-after: 600`.

18. **`CHAINLIT_URL` es obligatoria detras de un proxy que termina TLS.** En Container
    Apps el TLS termina en el ingress, asi que la app recibe una peticion `http://`
    interna y construye el `redirect_uri` de OAuth con ese esquema. Google lo compara
    literalmente con el `https://` registrado y rechaza el login. Chainlit resuelve la URL
    publica en `get_user_facing_url()`, cuyo docstring dice literalmente "Handles
    deployment with proxies (like cloud run)": si `CHAINLIT_URL` no esta definida, deja la
    URL de la peticion tal cual.

    En el Bicep se deriva del dominio del entorno
    (`https://${prefijo}-agent.${entorno.properties.defaultDomain}`) y no del FQDN de la
    propia app, que seria una referencia circular. El FQDN de ACA siempre es
    `<nombre-app>.<defaultDomain>`.

    Sintoma: `redirect_uri_mismatch` en Google aunque el URI registrado parezca correcto.
    Diagnostico en un comando:

    ```bash
    curl -s -o /dev/null -w "%{redirect_url}" https://<app>/auth/oauth/google
    ```

    Si el `redirect_uri` del querystring empieza por `http://`, es esto.

## CI/CD con OIDC: el subject no es el que dice la documentacion

19. **GitHub puede presentar el subject con identificadores inmutables.** La forma
    documentada es `repo:<owner>/<repo>:environment:<env>`, pero este repo presenta:

    ```
    repo:bitmarc@59296507/hxq-agent@1388231813:environment:production
    ```

    Incluye los IDs numericos del owner y del repo, para que renombrarlos no rompa la
    confianza federada. Una credencial con el formato clasico **no coincide** y el login
    falla con:

    ```
    AADSTS700213: No matching federated identity record found for presented assertion
    subject 'repo:...'
    ```

    El propio mensaje trae el subject presentado: hay que copiarlo literalmente y crear la
    credencial con el. Aqui estan registradas las cuatro combinaciones (clasica e
    inmutable, por rama y por environment) para no depender de cual emita GitHub.

20. **Un job con `environment:` cambia el subject.** Usa
    `:environment:<nombre>` en vez de `:ref:refs/heads/<rama>`. Con ambos declarados en el
    workflow, la credencial tiene que ser la del environment.

21. **`az role assignment create` falla con `MissingSubscription`** en este entorno, tanto
    con alcance de recurso como de resource group, y con el rol por nombre o por ID. El
    contexto de suscripcion, el provider y las lecturas funcionan: es la CLI. Se resuelve
    por REST:

    ```bash
    az rest --method PUT \
      --url "https://management.azure.com${SCOPE}/providers/Microsoft.Authorization/roleAssignments/$(uuidgen)?api-version=2022-04-01" \
      --body @cuerpo.json
    ```

22. **Los invitados SI pueden crear app registrations** si la politica del tenant lo
    permite. Comprobarlo antes de asumir lo contrario:

    ```bash
    az rest --method GET --url "https://graph.microsoft.com/v1.0/policies/authorizationPolicy" \
      --query "defaultUserRolePermissions.allowedToCreateApps"
    ```

## Fase 3: piezas graficas

23. **Azure bloquea generar imagenes de Pokemon.** `gpt-image-2` rechaza el prompt con
    `moderation_blocked` en la etapa de **output**, categoria `other`. Comprobado de
    forma aislada: la misma escena con y sin la palabra "Pokemon" da 400 y 200
    respectivamente. Es filtrado de propiedad intelectual, no de contenido sensible.

    Consecuencia de diseno: el arte generado sirve para ambiente (escenas, paisajes,
    grupos de personas), no para el Pokemon protagonista. Para eso el camino es el arte
    oficial, que es justo lo que usan las piezas publicadas.

24. **El endpoint de imagenes tambien es la superficie v1.** `AsyncAzureOpenAI` arma
    `/openai/deployments/<nombre>/images/generations` y responde 404. Lo que funciona es
    `AsyncOpenAI` con `base_url = <endpoint>/openai/v1/`, igual que el chat. Con API key
    hay que mandar la cabecera `api-key`, porque la SDK manda `Authorization: Bearer`.

25. **La API sincrona de Playwright no arranca dentro de un bucle asyncio**: "It looks
    like you are using Playwright Sync API inside the asyncio loop". Como las tools del
    agente son async, el motor usa `async_playwright` y expone un envoltorio sincrono
    para scripts y tests.

26. **Las rutas relativas del HTML se resuelven contra el archivo, no contra el paquete.**
    El HTML temporal tiene que escribirse en el mismo directorio que las plantillas o los
    `../tokens.css` apuntan fuera. El sintoma es desconcertante: la pieza sale en blanco
    con texto invisible, porque solo sobrevive el `<style>` inline y este deja
    `color: #fff` sobre el fondo blanco por defecto.

27. **Un hijo flex no baja de su tamano de contenido sin `min-height: 0`.** Con una altura
    fija en el arte central, una pieza con muchos detalles empujaba el pie fuera del
    lienzo y la captura lo recortaba. El arte ahora es `flex: 1 1 auto` con
    `min-height: 0` en el contenedor: absorbe el espacio libre y cede cuando los datos
    ocupan mas.

28. **`document.fonts.ready` antes de capturar.** Las fuentes cargan de forma asincrona;
    sin esperarlas la captura sale con la fuente del sistema y el texto ocupa otro ancho,
    asi que los cortes de linea no coinciden con lo que se ve en el navegador.

29. **PokéAPI sirve el arte oficial con canal alfa** en
    `sprites/pokemon/other/official-artwork/{id}.png` (512x512, ~120 KB). Es lo que
    permite montar el Pokemon sobre el fondo neon sin recuadro. El nombre en espanol vive
    en `/pokemon-species/`, no en `/pokemon/`, y el arte se indexa por numero de especie,
    no por el id de la forma.

30. **Nada se escribe bajo `/app` en el contenedor.** El proceso corre como usuario sin
    privilegios y `/app` es de root, asi que `Path.cwd() / "out"` falla con
    `[Errno 13] Permission denied` **solo en produccion**: en local el desarrollador es
    dueno de todo y no se reproduce.

    Ya paso dos veces (con `/app/.files` de Chainlit y con `/app/out` de las piezas), asi
    que ahora los archivos generados van a `settings.subdir(...)`, que cuelga de
    `HXQ_DATA_DIR` o del temporal del sistema. `tests/test_rutas_escritura.py` escanea el
    codigo en busca de rutas de escritura peligrosas para que no haya una tercera vez.

    Ojo con el falso negativo: escribir dentro del paquete (`Path(__file__).parent / ...`)
    funcionaba de casualidad porque el Dockerfile hace `COPY --chown=hxq:hxq src`. Sigue
    siendo mala practica y el test tambien lo caza.

31. **El resultado de una tool llega como `list[Content]`, no como `str`.** En un
    `@function_middleware`, `context.result` es una lista de objetos `Content`, asi que
    `str(context.result)` produce `[<agent_framework._types.Content object at 0x...>]`.

    Rompia dos cosas a la vez y sin ningun error visible: el panel de la tool mostraba
    ese repr, y el detector de archivos generados no encontraba ninguna ruta, asi que la
    imagen y el calendario nunca se le adjuntaban al admin. Los archivos se generaban
    correctamente y no habia forma de obtenerlos.

    Hay que extraer el texto recorriendo la lista y leyendo `.text` de cada elemento.
    Lo mismo aplica a `tool.invoke(...)`, que devuelve la misma forma.

## Personalizacion de la interfaz de Chainlit

32. **Los assets de marca se resuelven por glob en `public/`**: `logo_light.*`,
    `logo_dark.*` (la ruta es `/logo?theme=dark`), `favicon.*` y `theme.json`. Los SVG
    funcionan. Si no hay `favicon.*`, Chainlit sirve el suyo.

33. **`theme.json` lleva tripletes HSL sin envolver.** `"130 49% 48%"`, no
    `"hsl(130 49% 48%)"` ni `"#2D853C"`: el frontend los mete dentro de `hsl(...)` al
    construir las variables CSS. La forma es
    `{"variables": {"dark": {...}, "light": {...}}}`, y se inyecta como `window.theme`.

34. **La imagen del login trae un filtro oscuro por defecto y no se quita con una cadena
    vacia.** El frontend hace
    `login_page_image_dark_filter || "brightness-[0.2] grayscale"`, y `""` es falsy en
    JavaScript, asi que cae al default y el logo sale turbio. Hay que pasar una clase de
    Tailwind truthy que no haga nada, como `brightness-100`.

    Y si no se fija `login_page_image`, Chainlit estira el favicon para llenar el panel.
