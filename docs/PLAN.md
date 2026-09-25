# HXQ Agent — PRD y plan de implementación por fases

## Context

Una comunidad local de jugadores de Pokémon GO en México se administra hoy a mano: cada quedada, evento o aviso exige redactar el copy tres veces (Campfire, WhatsApp, Instagram), diseñar una pieza gráfica en Canva desde cero, y buscar a mano las fechas y bonus oficiales del evento. Los 2-5 administradores repiten ese ciclo varias veces por semana y el resultado es inconsistente en branding y ocasionalmente incorrecto en datos.

**Lo que se construye:** un agente conversacional privado, accesible por web, que los admins usan como copiloto de comunicación. Produce paquetes de contenido listos para publicar (copy por canal + imagen con branding + archivo de calendario) y responde dudas sobre eventos con fuentes citadas.

**Lo que NO se construye (y por qué):** publicación automática. Se verificó que Campfire (Niantic) no expone API pública —solo un bot Campfire→Discord de un solo sentido— y que la Groups API oficial de WhatsApp está topada en **8 participantes** y exige Official Business Account. Automatizar esos canales requeriría librerías no oficiales que violan los ToS de Meta y ponen en riesgo el número de la comunidad. Por tanto el producto es un **generador de paquetes**, con el humano dando el último clic. Esto no es una limitación del diseño: es la realidad de las plataformas en septiembre de 2026.

**Resultado esperado:** lo que hoy toma ~45 min por quedada (copy ×3 + imagen + investigar datos) baja a un turno de conversación y una revisión.

---

## 1. Decisiones tomadas

| Área | Decisión | Razón |
|---|---|---|
| Framework de agentes | **Microsoft Agent Framework 1.0** (GA abril 2026), Python | Sucesor de Semantic Kernel/AutoGen, APIs estables, LTS, OTel y MCP nativos |
| Arquitectura | **Un agente + tools** en v1; refactor a `HandoffBuilder` en Fase 5 | No pagar complejidad multi-agente antes de que el system prompt duela |
| Modelo de texto | `gpt-5.6-luna` (rápido, barato, 1M contexto, fuerte en multilingüe) | Encaja el presupuesto; `gpt-5.6-sol` reservado para tareas de razonamiento pesado si hace falta |
| Modelo de imagen | `gpt-image-1.5` — **solo para arte de fondo**, nunca para texto | `dall-e-3` fue retirado en marzo 2026 |
| Piezas gráficas | **Plantilla HTML/CSS (Jinja2) → Playwright → PNG**, con arte IA de fondo | Fecha, hora y lugar tienen que salir exactos; un modelo de imagen no garantiza eso |
| UI | **Chainlit** — aislada detrás de una capa fina | Ver riesgo R1: es community-maintained desde mayo 2025 |
| Auth | **Google OAuth directo** (provider nativo de Chainlit) + allowlist de correos | "Lo más sencillo": ~15 min, $0, cero infra. Entra External ID queda como camino de migración documentado |
| Hosting | **Azure Container Apps**, un contenedor | WebSockets y session affinity nativos, scale-to-zero, deploy desde Dockerfile |
| Base de datos | **Neon Postgres** (free tier, vía Azure Native ISV) | Es el data layer **oficial** de Chainlit (asyncpg) y cuesta $0; `pgvector` ya incluido para Fase 6 |
| Almacenamiento binario | **Azure Blob Storage** | Chainlit lo soporta nativamente como storage provider de elements |
| Búsqueda web | **Tavily** (1.000 créditos/mes gratis) con `include_domains` | Bing Grounding cuesta $14/1.000 búsquedas; Brave eliminó su free tier en feb 2026 |
| Clima | **Open-Meteo** | Gratis, sin API key |
| Calendario | **archivo `.ics`** generado al vuelo | Cero credenciales, funciona con Google/Apple/Outlook; Google Calendar API queda para fase posterior |
| Región/locale | `America/Mexico_City`, español de México, hora 12h am/pm, fecha dd/mm | Comunidad en México |

---

## 2. Arquitectura

```
Google OAuth ──► Chainlit (Azure Container Apps, 1 contenedor)
                   │  @cl.oauth_callback  → valida contra allowlist
                   │  @cl.on_chat_start   → agent.create_session()
                   │  @cl.on_message      → agent.run(stream=True)  [streaming + cl.Step por tool]
                   ▼
              Microsoft Agent Framework 1.0
              Agent(OpenAIChatClient(azure_endpoint=...))
                 ├─ buscar_web(query, ambito)        → Tavily  (ámbito "oficial" = dominios acotados)
                 ├─ consultar_clima(lugar, fecha)    → Open-Meteo
                 ├─ generar_arte(prompt, formato)    → gpt-image-1.5 → Blob
                 ├─ render_pieza(plantilla, datos)   → Jinja2 → Playwright → PNG → Blob
                 ├─ crear_ics(evento)                → icalendar → cl.File
                 ├─ guardar_en_biblioteca(pieza)     → Postgres + Blob
                 └─ buscar_en_biblioteca(query)      → Postgres
                   ▼
   Neon Postgres (historial Chainlit + biblioteca de contenido)
   Azure Blob Storage (imágenes, elements)
   Azure OpenAI / Foundry (gpt-5.6-luna, gpt-image-1.5) — vía Managed Identity
```

**Regla de oro del diseño:** nada bajo `src/hxq_agent/agent/` importa `chainlit`. El agente y sus tools son librería pura, testeable sin UI. Chainlit solo vive en `app.py` y `auth.py`. Esto es lo que hace que el riesgo R1 sea manejable.

### Estructura de repo

```
hxq-agent/
├─ src/hxq_agent/
│  ├─ app.py                    # entrypoint Chainlit: callbacks, streaming, actions
│  ├─ auth.py                   # @cl.oauth_callback + allowlist
│  ├─ ui/
│  │  ├─ starters.py            # un starter por tarea de uso.txt
│  │  ├─ settings.py            # cl.ChatSettings: tono, canal destino, formato
│  │  └─ actions.py             # Aprobar / Regenerar copy / Regenerar imagen / Descargar zip
│  ├─ agent/
│  │  ├─ factory.py             # build_agent() ← punto único de refactor a HandoffBuilder
│  │  ├─ instructions.py        # system prompt versionado
│  │  └─ tools/
│  │     ├─ search.py  weather.py  imaging.py
│  │     ├─ rendering.py  calendar.py  library.py
│  ├─ brand/
│  │  ├─ tokens.css             # colores y tipografías de la comunidad
│  │  ├─ templates/*.html.j2    # quedada, anuncio, infografía, dinámica
│  │  └─ assets/                # logo, texturas
│  ├─ schemas/                  # modelos Pydantic: Quedada, Evento, Pieza, Dinamica
│  ├─ storage/                  # blob.py, db.py (SQLAlchemy)
│  └─ config.py                 # pydantic-settings
├─ .chainlit/config.toml        # transports=["websocket"], tema, features
├─ public/                      # logo, favicon, theme.json de Chainlit
├─ chainlit.md                  # pantalla de bienvenida
├─ tests/
├─ Dockerfile
├─ pyproject.toml               # gestionado con uv, Python 3.13
├─ infra/main.bicep             # ACA env, ACA app, Storage, identidad, secretos
└─ .github/workflows/deploy.yml
```

---

## 3. Fases

### Fase 0 — Cimientos locales

- Scaffold con `uv`, Python 3.13, `pyproject.toml`. Dependencias: `agent-framework`, `chainlit`, `pydantic-settings`, `httpx`, `jinja2`, `playwright`, `icalendar`, `sqlalchemy[asyncio]`, `asyncpg`.
- **Primer paso obligatorio:** `uv add agent-framework` y verificar los import paths reales contra la versión instalada (ver `docs/API-VERIFICADA.md`). MAF 1.0 es GA pero la superficie de `agent_framework_orchestrations` y Agent Harness es reciente — confirmar, no asumir.
- Chainlit + un `Agent` contra Azure OpenAI con streaming token a token.
- `auth.py`: `@cl.oauth_callback` con Google, allowlist desde `HXQ_ADMIN_EMAILS` (lista separada por comas).
- Provisionar en Azure: recurso de Azure OpenAI (o proyecto Foundry) + deployments de `gpt-5.6-luna` y `gpt-image-1.5`. **Confirmar la región** por disponibilidad de ambos modelos antes de crear nada.

**Verificación:** `chainlit run src/hxq_agent/app.py -w`; login con tu Gmail funciona, un correo fuera de la allowlist es rechazado, la respuesta llega en streaming.

### Fase 1 — Agente conversacional con búsqueda web *(el alcance que pediste "de momento")*

- `buscar_web(query, ambito)` sobre Tavily con dos modos: `ambito="oficial"` restringe a `pokemongolive.com`, `leekduck.com`, `serebii.net` vía `include_domains`; `ambito="abierto"` busca libre.
- `consultar_clima(lugar, fecha)` sobre Open-Meteo, para logística de quedadas.
- `instructions.py`: contexto de la comunidad, timezone `America/Mexico_City`, formato 12h, español de México. **Reglas duras:** nunca inventar una fecha ni un bonus de evento; si la búsqueda no devuelve nada, decirlo explícitamente; toda afirmación sobre un evento oficial va con enlace a la fuente.
- Chainlit: `cl.Starter` por cada tarea de `uso.txt`, `cl.ChatSettings` (tono, canal destino, longitud), `cl.Step` para que cada llamada a tool sea visible.

**Verificación:** preguntar "¿qué hay para el próximo Community Day?" y comprobar que la respuesta cita una fuente oficial real y no inventa la fecha. Preguntar por un evento inexistente y comprobar que dice que no encontró nada.

### Fase 2 — Persistencia y despliegue en Azure

- Proyecto Neon (free tier) → `DATABASE_URL` → data layer oficial de Chainlit. Aplicar el esquema oficial de Chainlit + tabla `pieza` de la biblioteca.
- Azure Blob Storage como storage provider de elements.
- `Dockerfile` sobre `mcr.microsoft.com/playwright/python` (trae chromium y sus deps de sistema ya instalados), o `python:3.13-slim` + `playwright install --with-deps chromium-headless-shell` para una imagen más chica.
- Arranque: `chainlit run app.py --host 0.0.0.0 --port 8000 --headless` — las tres banderas son necesarias; `--host 0.0.0.0` es el clásico "funciona en local, 502 en producción".
- ACA: ingress externo, **session affinity activada**, `transports = ["websocket"]` en `.chainlit/config.toml`, Managed Identity para Azure OpenAI y Blob, secretos (client secret de Google, Tavily key, `DATABASE_URL`) como ACA secrets.
- Escalado: `min-replicas=0` durante desarrollo. Si el cold start (20-40s por chromium) molesta, subir a `min-replicas=1` con 0.25-0.5 vCPU — en tarifa idle de ACA sale ~$5-12/mes — o usar el **KEDA cron scaler** para mantener 1 réplica solo en horario activo (p.ej. 18:00-23:00) y 0 el resto.
- CI/CD: GitHub Actions → **GHCR** (no ACR Basic, que son $5/mes fijos) → `az containerapp update`.
- Observabilidad: OTel de MAF → Application Insights (tier gratuito de 5 GB/mes es de sobra).

**Verificación:** URL pública responde, login con Google funciona con el redirect URI de producción, una conversación de ayer sigue en el historial tras recargar, un `git push` a main redespliega solo.

### Fase 3 — Motor de piezas gráficas

Es la parte técnicamente más difícil y la que define si el producto se usa o no.

- Sistema de diseño a partir de los assets reales de la comunidad (logo, paleta, piezas anteriores — **los necesito para empezar esta fase**): `tokens.css` con colores y tipografías, y 4 plantillas Jinja2: `quedada`, `anuncio_evento`, `infografia_datos`, `dinamica`.
- `render_pieza(plantilla, datos)`: valida `datos` con el modelo Pydantic de la plantilla → renderiza HTML → `page.screenshot()` → PNG → Blob → devuelve `cl.Image`.
- Formatos de salida: 1080×1350 (feed IG), 1080×1920 (story), 1200×630 (Facebook).
- `generar_arte(prompt, formato)`: `gpt-image-1.5` solo para el fondo/ilustración, cacheado en Blob por hash del prompt para no pagar dos veces lo mismo.
- Manejo de texto largo: CSS con `clamp()` y truncado explícito, más un test que renderice cada plantilla con el string más largo plausible.

**Verificación:** generar la misma quedada 5 veces seguidas y comprobar que fecha, hora y lugar salen idénticos y correctos, y que el branding no varía entre generaciones. Comparar una pieza con una hecha a mano en Canva y que un admin diga cuál prefiere.

### Fase 4 — Paquete de quedada completo *(tu prioridad #1)*

El flujo de mayor retorno: `uso.txt` #2 + #3 + #5 resueltos de un tirón.

- Extracción de datos del mensaje libre → si falta algo (lugar, hora, fecha), preguntarlo; nunca asumir una hora.
- Salida en un solo turno:
  - **Bloque Campfire:** título, descripción, lugar, fecha y hora, en el formato que pide la app.
  - **Bloque WhatsApp:** corto, con emojis, llamada a la acción, listo para pegar en la comunidad.
  - **Bloque Instagram/Facebook:** caption + hashtags.
  - **Imagen** en los 3 formatos.
  - **`.ics`** descargable.
- `cl.Action`: `Aprobar` / `Regenerar copy` / `Regenerar imagen` / `Descargar todo (zip)`.
- Al aprobar: se archiva en la biblioteca (Postgres + Blob) con fecha, tipo, canal y el prompt que lo produjo.

**Verificación end-to-end:** generar una quedada real de la comunidad, pegar los tres bloques en Campfire, WhatsApp e Instagram **sin editar ni una palabra**, e importar el `.ics`. Si hay que editar, el prompt o la plantilla no están listos.

### Fase 5 — Multi-agente y dinámicas

- Refactor de `factory.py` a `HandoffBuilder(participants=[triage, contenido, diseno, eventos, research]).with_start_agent(triage).add_handoff(triage, [...]).build()`. Las tools no cambian; solo se reparten.
- Tool de dinámicas y concursos (`uso.txt` #6): reglas, premios, criterios de desempate, duración.
- `buscar_en_biblioteca(query)` para no repetir una dinámica que ya se hizo hace un mes.
- Evaluar `create_harness_agent` (Agent Harness) por la compactación automática de contexto, útil cuando las conversaciones de planificación se alarguen.

**Verificación:** el set de pruebas de las fases 1-4 pasa igual o mejor con la arquitectura nueva; las trazas de App Insights muestran los handoffs y no hay bucles de enrutamiento.

### Fase 6 — Conocimiento propio y datos de jugadores

- Ingesta de documentos de la comunidad (reglas, histórico de eventos, acuerdos) → embeddings → **`pgvector` en Neon** ($0). Resuelve `uso.txt` #4 y #7 con fuentes propias además de la web.
- `uso.txt` #8 y #9 (métricas y lista de jugadores) **no entran aquí todavía**: confirmaste que ni la lista ni el origen de las métricas existen definidos. Requieren una entrevista propia antes de diseñarse. Cuando se haga, el candidato técnico es extracción por visión de screenshots de perfil con `gpt-5.6` + tabla en Neon.
- Opcional si duele: Google Calendar API sobre un calendario público de la comunidad, reemplazando el `.ics`.

---

## 4. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Chainlit es community-maintained** desde mayo 2025 (última release 2.12.0, ago 2026). Podría estancarse. | El core no importa `chainlit`. Migrar a FastAPI+Next o a DevUI de MAF sería trabajo de días. Fijar la versión en `pyproject.toml`. |
| R2 | **Campfire y WhatsApp sin API usable.** Tentación de usar librerías no oficiales de WhatsApp Web. | Fuera del alcance, explícitamente: violan los ToS de Meta y arriesgan el número de la comunidad. El producto entrega contenido listo para pegar. |
| R3 | **Alucinación de fechas y bonus de eventos** — un dato falso se publica a toda la comunidad. | Búsqueda acotada a dominios oficiales, cita obligatoria, prohibición explícita de inventar fechas, y aprobación humana antes de publicar. |
| R4 | **Texto ilegible o mal escrito en imágenes** generadas por IA. | Los datos duros nunca los escribe el modelo de imagen: van en la plantilla HTML. |
| R5 | **Cold start de 20-40s** por chromium en la imagen. | `chromium-headless-shell`, y `min-replicas=1` o KEDA cron scaler en horario activo. |
| R6 | **Presupuesto <$25/mes** con Playwright y modelo de imagen. | Proyección: ACA $0-12, Azure OpenAI $3-8, Neon $0, Blob ~$0.50, GHCR $0, Tavily $0, App Insights $0 → **~$4-20/mes**. Alerta de presupuesto en Azure Cost Management desde la Fase 2. |
| R7 | Créditos de Tavily agotados (1.000/mes). | Caché de búsquedas por query+día en Postgres; una búsqueda repetida no consume crédito. |

---

## 5. Criterios de calidad

Una salida es buena cuando:
1. **Se publica sin editar.** Copiar y pegar en Campfire/WhatsApp/Instagram sin tocar una palabra.
2. **Los datos duros son correctos.** Fecha, hora y lugar coinciden con lo que pidió el admin. Cero tolerancia.
3. **El branding es indistinguible** de una pieza hecha a mano por la comunidad.
4. **Toda afirmación sobre un evento oficial tiene fuente enlazada.**
5. **El tono suena a la comunidad**, no a asistente corporativo: español de México, cercano, con los modismos que ya usan.
6. **Nunca publica solo.** Ninguna acción sale del sistema sin un clic humano.

---

## 6. Ambigüedades pendientes

1. **Assets de branding** — logo, paleta exacta, tipografías y 2-3 piezas anteriores. Bloquean la Fase 3, no las anteriores.
2. **Esquema de jugadores y métricas** — sin definir. Entrevista aparte antes de la Fase 6.
3. **Suscripción y región de Azure** — confirmar que hay suscripción activa y elegir región con `gpt-5.6-luna` *y* `gpt-image-1.5` disponibles, más la quota concedida.
4. **Cuenta de Google Cloud** para el OAuth client (es gratis, pero hay que crear el proyecto y registrar el redirect URI).
5. **Tono de voz** — convendría capturar 3-4 avisos reales ya publicados para extraer el estilo en vez de inventarlo.

---

## 7. Siguiente acción

Ejecutar **Fase 0**: scaffold con `uv`, verificar los import paths reales de `agent-framework` 1.0, y levantar Chainlit + un `Agent` con Google OAuth funcionando en local. Es la fase que valida los dos supuestos más importantes (que MAF y Chainlit se integran limpiamente con streaming, y que el OAuth de Google es tan simple como se espera) antes de invertir en nada más.
