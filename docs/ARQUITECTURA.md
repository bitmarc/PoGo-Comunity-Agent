# Arquitectura de HuixquiGo Agent

Cómo está montada la aplicación y cómo viajan los mensajes entre sus piezas.
Refleja el estado del código a 27 de septiembre de 2026 (fases 0 a 5 completadas).

Para el *qué* y el *por qué* del producto, ver [`PLAN.md`](PLAN.md).
Para las trampas concretas de cada librería, [`API-VERIFICADA.md`](API-VERIFICADA.md).

---

## 1. Panorama general

El agente vive en un solo contenedor en Azure Container Apps. Todo lo que hay alrededor
son servicios gestionados o APIs públicas.

```mermaid
flowchart TB
    admin["Administrador<br/>(navegador)"]

    subgraph azure["Azure Container Apps · westus3"]
        app["hxq-agent<br/>Chainlit + Agent Framework<br/>1 réplica, escala a cero"]
    end

    subgraph datos["Estado"]
        neon[("Neon Postgres<br/>historial + biblioteca")]
        blob[("Azure Blob<br/>imágenes aprobadas")]
    end

    subgraph modelos["Modelos"]
        aoai["Azure OpenAI<br/>gpt-5.6-luna · gpt-image-2"]
    end

    subgraph externos["APIs públicas"]
        tavily["Tavily<br/>búsqueda web"]
        meteo["Open-Meteo<br/>clima"]
        pokeapi["PokéAPI<br/>arte oficial y tipos"]
    end

    obs["Application Insights"]

    admin -->|"HTTPS + WebSocket"| app
    app -->|"OAuth"| google["Google<br/>identidad"]
    app <-->|"asyncpg / TLS"| neon
    app -->|"Managed Identity"| blob
    app -->|"Managed Identity"| aoai
    app --> tavily
    app --> meteo
    app --> pokeapi
    app -.->|"OpenTelemetry"| obs

    classDef nuestro fill:#1b5e20,stroke:#4ade80,color:#fff
    classDef externo fill:#263238,stroke:#78909c,color:#fff
    class app nuestro
    class tavily,meteo,pokeapi,google externo
```

**Sin claves de larga vida hacia Azure.** El acceso a Azure OpenAI y a Blob Storage va
con la identidad administrada del contenedor. Las únicas credenciales que existen son las
de Google OAuth, Tavily y Neon, y viven como secretos de la Container App.

---

## 2. La frontera que gobierna el diseño

Hay una sola regla estructural, y de ella cuelga casi todo lo demás:

> **Nada bajo `agent/`, `brand/` o `schemas/` importa `chainlit`.**

Chainlit es *community-maintained* desde mayo de 2025. Aislarlo detrás de una capa fina
significa que cambiar de interfaz —a FastAPI + React, o al DevUI de Agent Framework— es
trabajo de días y no de semanas. Y como efecto secundario, el núcleo se prueba sin
levantar la app.

```mermaid
flowchart TB
    subgraph capa_ui["Capa UI · SÍ importa chainlit"]
        appmod["app.py<br/>callbacks y streaming"]
        authmod["auth.py<br/>binding de OAuth"]
        steps["ui/steps.py<br/>tools visibles + adjuntos"]
        acciones["ui/acciones.py<br/>aprobar / descartar"]
        ajustes["ui/settings.py · ui/starters.py"]
    end

    subgraph nucleo["Núcleo · NO importa chainlit"]
        factory["agent/factory.py"]
        instr["agent/instructions.py"]
        tools["agent/tools/*"]
        brand["brand/*<br/>render, arte, tipos, pokemon"]
        schemas["schemas/piezas.py"]
        access["access.py<br/>quién pasa"]
    end

    subgraph infra["Infraestructura"]
        config["config.py"]
        storage["storage/*"]
        obs["observability.py"]
    end

    appmod --> factory
    appmod --> steps
    appmod --> acciones
    appmod --> ajustes
    appmod --> obs
    appmod --> storage
    authmod --> access
    acciones --> storage
    factory --> instr
    factory --> tools
    tools --> brand
    tools --> schemas
    tools --> storage
    brand --> schemas
    factory --> config
    tools --> config
    access --> config
    storage --> config

    classDef ui fill:#4a148c,stroke:#ce93d8,color:#fff
    classDef core fill:#1b5e20,stroke:#4ade80,color:#fff
    classDef inf fill:#263238,stroke:#78909c,color:#fff
    class appmod,authmod,steps,acciones,ajustes ui
    class factory,instr,tools,brand,schemas,access core
    class config,storage,obs inf
```

`access.py` existe separado de `auth.py` por esa regla y por una razón práctica:
`@cl.oauth_callback` revienta al importarse si no hay proveedor configurado, así que la
lógica de quién entra no se podría probar sin montar OAuth.

`storage/` es la excepción parcial: el *data layer* es una interfaz de Chainlit, así que
`storage/db.py` la importa. `storage/biblioteca.py` y `storage/blob.py` no dependen de
ella para su lógica.

---

## 3. Un turno de conversación

Lo que pasa desde que el admin escribe hasta que ve la respuesta.

```mermaid
sequenceDiagram
    actor Admin
    participant App as app.py
    participant Instr as instructions.py
    participant Agent as Agent (MAF)
    participant Mw as ui/steps.py<br/>middleware
    participant Tool as tool
    participant AOAI as Azure OpenAI

    Admin->>App: escribe un mensaje
    App->>Instr: build_instructions()
    Note over Instr: se reconstruyen CADA turno:<br/>refrescan la fecha de hoy y<br/>aplican las preferencias del chat
    App->>Agent: run(stream=True, session, middleware, options)

    Agent->>AOAI: mensajes + instrucciones + esquemas de tools
    AOAI-->>Agent: decide llamar a una tool

    Agent->>Mw: intercepta la invocación
    Mw->>Admin: abre un paso colapsable
    Mw->>Tool: call_next()
    Tool-->>Mw: list[Content]
    Note over Mw: texto_resultado() extrae el texto.<br/>str() daría "[<Content object at 0x...>]"
    Mw->>Admin: muestra la salida en el paso
    Mw->>Admin: adjunta PNG / .ics si los hay

    Agent->>AOAI: resultado de la tool
    AOAI-->>Agent: respuesta final en streaming
    loop por cada token
        Agent-->>App: update.text
        App-->>Admin: stream_token()
    end

    App->>App: tomar_pendientes()
    alt se generó alguna pieza
        App->>Admin: botones Aprobar / Descartar
    end
```

Dos decisiones de orden que importan:

- **Las instrucciones se reconstruyen por turno**, no una vez por sesión. Así la fecha de
  hoy se recalcula (relevante si una pestaña queda abierta pasada la medianoche) y los
  controles del chat aplican de inmediato.
- **Los botones de aprobación salen al cerrar el turno**, no cuando termina la tool. El
  copy por canal lo escribe el agente *después* de dibujar la pieza; un botón junto a la
  imagen archivaría la pieza sin el texto que la acompaña.

---

## 4. El paquete de quedada

El flujo insignia: de una frase suelta a todo lo necesario para anunciar una quedada.

```mermaid
flowchart TD
    inicio["'Quedada el sábado a las 6<br/>en el Parque, con Rayquaza'"]
    faltan{"¿Hay lugar,<br/>fecha y hora?"}
    pregunta["Pregunta SOLO lo que falta<br/>y para ahí"]

    render["render_pieza"]
    pokeapi["PokéAPI:<br/>arte oficial + tipos reales"]
    acentos["Los tipos fijan<br/>los colores de la pieza"]
    png["PNG 1240x1240"]

    ics["crear_ics"]
    clima["consultar_clima<br/>(si es al aire libre)"]

    copy["Tres bloques de copy"]
    campfire["Campfire<br/>sin repetir lugar ni hora:<br/>la app los pide aparte"]
    wa["WhatsApp<br/>corto, con los datos SIEMPRE:<br/>se lee sin abrir la imagen"]
    ig["Instagram / Facebook<br/>gancho en la 1ª línea<br/>+ hashtags"]

    aprobar{"¿Aprobar?"}
    biblio[("Biblioteca:<br/>Blob + Postgres")]
    nada["No se archiva"]

    inicio --> faltan
    faltan -->|no| pregunta
    faltan -->|sí| render
    render --> pokeapi --> acentos --> png
    render --> ics
    render --> clima
    png --> copy
    copy --> campfire & wa & ig
    campfire & wa & ig --> aprobar
    aprobar -->|sí| biblio
    aprobar -->|no| nada

    classDef dato fill:#0d47a1,stroke:#64b5f6,color:#fff
    classDef salida fill:#1b5e20,stroke:#4ade80,color:#fff
    class png,ics dato
    class campfire,wa,ig salida
```

Los tres bloques son deliberadamente distintos, no el mismo texto recortado. Cada canal
tiene restricciones propias y el agente las conoce por instrucción.

---

## 5. Motor de piezas gráficas

Por qué una plantilla HTML y no un modelo de imagen: **fecha, hora y lugar tienen que
salir exactos**. Un modelo de imagen los escribe mal lo bastante a menudo como para que
no sirva, y una pieza con la hora equivocada llega a toda la comunidad.

```mermaid
flowchart LR
    datos["datos JSON<br/>del agente"]
    valida["schemas/piezas.py<br/>modelo Pydantic"]
    error["Error accionable:<br/>'falta el lugar'"]

    subgraph arte_sub["Arte central (opcional)"]
        direction TB
        pkmn["brand/pokemon.py<br/>PokéAPI"]
        gen["brand/arte.py<br/>gpt-image-2"]
    end

    tipos["brand/tipos.py<br/>tipos → acentos"]
    jinja["Jinja2<br/>base + plantilla"]
    css["tokens.css<br/>neón, tarjetas, pie"]
    chromium["Playwright<br/>Chromium headless"]
    png["PNG 1240x1240"]

    datos --> valida
    valida -->|"no válida"| error
    valida -->|"válida"| tipos
    valida --> arte_sub
    pkmn --> tipos
    tipos --> jinja
    css --> jinja
    arte_sub --> jinja
    jinja --> chromium --> png

    classDef malo fill:#b71c1c,stroke:#ef9a9a,color:#fff
    class error malo
```

**El arte oficial gana sobre el generado.** Además de que Azure rechaza generar propiedad
intelectual (`moderation_blocked`), un Pokémon dibujado por IA se nota y no es el que la
gente espera ver. `gpt-image-2` queda para ambiente: escenas, paisajes, grupos de gente.

Y los tipos que devuelve PokéAPI no son decorativos: **de ellos salen los colores**. Una
pieza de Cottonee sale verde y rosa porque la API dice `grass`/`fairy`, no porque nadie lo
escribiera. Si los dos tipos dan colores parecidos (Rayquaza es Dragón/Volador, ambos
violeta), el secundario cede ante uno que contraste.

---

## 6. Persistencia

Dos almacenes con responsabilidades distintas, y un tercero efímero que conviene conocer.

```mermaid
flowchart TB
    subgraph efimero["Efímero · /tmp del contenedor"]
        tmp["piezas y .ics recién generados<br/>caché de arte y de PokéAPI"]
    end

    subgraph durable["Durable"]
        pg[("Neon Postgres")]
        bl[("Azure Blob")]
    end

    subgraph tablas["Tablas en Postgres"]
        chainlit["User · Thread · Step<br/>Element · Feedback<br/>(esquema del upstream)"]
        pieza["pieza<br/>(nuestro)"]
    end

    tmp -->|"al Aprobar"| bl
    tmp -->|"al Aprobar"| pg
    pg --- chainlit
    pg --- pieza
    pieza -.->|"imagen_object_key"| bl

    classDef warn fill:#4e342e,stroke:#ffab91,color:#fff
    class tmp warn
```

**Lo de `/tmp` desaparece cuando la réplica se apaga.** Como la app escala a cero, una
imagen de ayer no seguirá ahí mañana. Para el flujo *generar → revisar → pegar → publicar*
eso basta; para conservar el histórico está el botón de aprobar.

**Solo se archiva lo aprobado.** Guardar cada borrador llenaría la tabla de ruido y
volvería inútil la búsqueda.

**Si Blob falla, la fila se guarda igual, sin imagen.** Perder el registro entero porque
faltó configurar el almacenamiento sería peor que perder la imagen.

---

## 7. Autenticación

```mermaid
sequenceDiagram
    actor Admin
    participant Chainlit
    participant Google
    participant Auth as auth.py
    participant Access as access.py

    Admin->>Chainlit: "Continuar con Google"
    Chainlit->>Google: redirect_uri desde CHAINLIT_URL
    Note over Chainlit,Google: sin CHAINLIT_URL se construiría con http://<br/>porque el TLS termina en el ingress,<br/>y Google lo rechaza
    Google-->>Chainlit: código
    Chainlit->>Google: intercambio + perfil
    Chainlit->>Auth: oauth_callback(perfil)
    Auth->>Access: extract_email · email_is_verified · is_allowed
    alt correo en HXQ_ADMIN_EMAILS
        Access-->>Auth: autorizado
        Auth-->>Chainlit: User con rol admin
        Chainlit-->>Admin: entra
    else cualquier otro caso
        Access-->>Auth: denegado
        Auth-->>Chainlit: None
        Chainlit-->>Admin: acceso rechazado
    end
```

La allowlist vacía **niega a todos**. Un despliegue mal configurado no debe convertirse en
barra libre.

---

## 8. Despliegue

```mermaid
flowchart LR
    push["git push a main"]

    subgraph ci["GitHub Actions"]
        direction TB
        test["test<br/>ruff + 210 pytest<br/>(con Chromium real)"]
        build["build<br/>imagen → GHCR<br/>tag = SHA del commit"]
        deploy["deploy<br/>OIDC, sin secretos"]
    end

    aca["Container App<br/>revisión nueva"]
    smoke["curl de comprobación"]

    push --> test
    test -->|"pasa"| build
    test -->|"falla"| stop["No se construye<br/>ni se despliega"]
    build --> deploy --> aca --> smoke

    classDef malo fill:#b71c1c,stroke:#ef9a9a,color:#fff
    class stop malo
```

La imagen se etiqueta con el SHA del commit, no con `latest`: así siempre se sabe qué está
desplegado y se puede volver atrás.

El login a Azure usa **OIDC federado**, sin secreto de service principal que rotar. El
`subject` del token lleva identificadores inmutables
(`repo:bitmarc@59296507/hxq-agent@1388231813:environment:production`), no el formato
documentado — ver `API-VERIFICADA.md` #19.

---

## 9. Configuración

Todo entra por variables de entorno y lo lee un único módulo, `config.py`. Ningún otro
sitio toca `os.environ`.

| Variable | Si falta |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | La app no arranca la conversación, con mensaje claro |
| `AZURE_OPENAI_API_KEY` | Se usa Managed Identity (`az login` en local) |
| `OAUTH_GOOGLE_CLIENT_ID` / `_SECRET` | La app **no arranca**: mejor eso que sin puerta |
| `CHAINLIT_AUTH_SECRET` | Chainlit no firma sesiones |
| `CHAINLIT_URL` | El login falla en producción con `redirect_uri_mismatch` |
| `HXQ_ADMIN_EMAILS` | Nadie entra |
| `TAVILY_API_KEY` | Conversa, pero **no verifica datos de eventos** y lo avisa |
| `DATABASE_URL` | Corre sin historial ni biblioteca |
| `AZURE_STORAGE_ACCOUNT` / `_CONTAINER` | Archiva sin imagen |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Sin telemetría |
| `HXQ_DATA_DIR` | Usa el temporal del sistema |
| `AZURE_OPENAI_API_VERSION` | **Déjala vacía.** Fijarla rompe con `400 API version not supported` |

El patrón es deliberado: **degradar antes que caer**. Una funcionalidad sin configurar se
apaga y lo dice; solo la ausencia de puerta de entrada impide arrancar.

---

## 10. Dónde tocar según qué

| Quiero… | Empezar por |
|---|---|
| Cambiar cómo habla o qué reglas sigue | `agent/instructions.py` |
| Añadir una capacidad nueva | `agent/tools/` + registrarla en `tools/__init__.py` |
| Cambiar el aspecto de las piezas | `brand/tokens.css` y `brand/templates/` |
| Añadir un tipo de pieza | `schemas/piezas.py` + plantilla + `PLANTILLAS` |
| Cambiar el aspecto de la app | `public/theme.json` y `.chainlit/config.toml` |
| Tocar infraestructura | `infra/main.bicep` |
| Cambiar el esquema de la base | `infra/db/` y `apply_schema.py` |

Antes de escribir código nuevo conviene mirar `API-VERIFICADA.md`: recoge 34 detalles
comprobados contra las librerías reales, varios de los cuales cuestan una tarde cada uno.
