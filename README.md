# HXQ Agent

Agente copiloto de comunicacion para los administradores de una comunidad local de Pokemon GO
(Mexico). Genera paquetes de contenido listos para publicar: copy por canal, imagen con el
branding de la comunidad y archivo de calendario.

Stack: Microsoft Agent Framework 1.x + Chainlit, desplegado en Azure Container Apps.

**En produccion:** https://hxq-agent.whitefield-f29520c3.westus3.azurecontainerapps.io
(acceso restringido por allowlist de correos).
Documentacion:

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — como esta montada la app y como viajan
  los mensajes entre sus piezas, con diagramas
- [`docs/PLAN.md`](docs/PLAN.md) — el plan por fases y su estado
- [`docs/API-VERIFICADA.md`](docs/API-VERIFICADA.md) — detalles comprobados contra las
  librerias reales, varios de los cuales cuestan una tarde
- [`docs/DATOS-POKEMON.md`](docs/DATOS-POKEMON.md) — fuentes de datos y sus condiciones
Superficie de API verificada (y las trampas) en [`docs/API-VERIFICADA.md`](docs/API-VERIFICADA.md).

## Desarrollo local

El entorno virtual ya existe en `.venv/`. **No hace falta ninguna herramienta extra para
correr el proyecto**: todos los ejecutables estan dentro de `.venv\Scripts\`.

### 1. Configurar el entorno

```powershell
Copy-Item .env.example .env
# Rellena .env. El secreto de sesion lo generas asi:
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Arrancar

```powershell
.\.venv\Scripts\chainlit.exe run src\hxq_agent\app.py -w
```

Abre http://localhost:8000. El `-w` recarga en caliente al guardar un archivo.

### 3. Pruebas y linter

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format src tests
```

### Alternativa: activar el venv

Si prefieres no escribir la ruta cada vez:

```powershell
.\.venv\Scripts\Activate.ps1
chainlit run src\hxq_agent\app.py -w
pytest -q
```

Si PowerShell bloquea el script de activacion:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Sobre uv

[uv](https://docs.astral.sh/uv/) es el gestor de paquetes y entornos (de Astral, los de
ruff): hace lo de `pip` + `venv` + lockfile, mucho mas rapido y reproducible. Este proyecto
lo usa para mantener `uv.lock`, pero **solo se necesita para cambiar dependencias**, no para
ejecutar.

En esta maquina `uv.exe` esta instalado en
`C:\Users\marco\AppData\Roaming\Python\Python313\Scripts\`, que **no esta en el PATH**.
Para dejarlo disponible como comando `uv` en cualquier terminal nueva:

```powershell
$uvDir = "$env:APPDATA\Python\Python313\Scripts"
[Environment]::SetEnvironmentVariable(
    "Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";$uvDir",
    "User"
)
# Cierra y reabre la terminal, luego: uv --version
```

Una vez en el PATH:

```powershell
uv sync --extra dev      # recrear el entorno desde uv.lock
uv add <paquete>         # anadir dependencia y actualizar el lock
uv run pytest -q         # ejecutar dentro del entorno del proyecto
```

## Historial persistente (opcional en local)

Sin `DATABASE_URL` la app funciona, pero las conversaciones se pierden al recargar.
Para tener historial en local, un Postgres en Docker:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe infra/db/apply_schema.py
```

Y en `.env`:

```
DATABASE_URL=postgresql://postgres:devpass@localhost:55432/hxqdev
```

En produccion es [Neon](https://neon.tech) en plan Free. El esquema es el mismo: solo
cambia la cadena de conexion.

## Despliegue

```powershell
# 1. Parametros
Copy-Item infra/main.parameters.example.json infra/main.parameters.json   # y rellenar

# 2. Infraestructura (crea identidad, storage, logs, insights, Container App)
az deployment group create -g <resource-group> `
  --template-file infra/main.bicep `
  --parameters @infra/main.parameters.json

# 3. Esquema en Neon
$env:DATABASE_URL="<cadena de Neon>"
.\.venv\Scripts\python.exe infra/db/apply_schema.py
```

El despliegue imprime `urlApp` y `redirectUriGoogle`: ese redirect URI hay que **anadirlo
en Google Cloud Console** junto al de localhost, o el login fallara en produccion.

Despues, cada push a `main` reconstruye la imagen en GHCR y actualiza la Container App
(`.github/workflows/deploy.yml`).

## Configuracion requerida

| Variable | Para que |
|---|---|
| `OAUTH_GOOGLE_CLIENT_ID` / `_SECRET` | Login con Google. Redirect URI: `http://localhost:8000/auth/oauth/google/callback` |
| `CHAINLIT_AUTH_SECRET` | Firma de la sesion |
| `HXQ_ADMIN_EMAILS` | Allowlist de correos, separados por coma. Vacia = nadie entra |
| `AZURE_OPENAI_ENDPOINT` | Recurso de Azure OpenAI |
| `AZURE_OPENAI_API_KEY` | Opcional: si se omite se usa `DefaultAzureCredential` (Managed Identity / `az login`) |
| `TAVILY_API_KEY` | Busqueda web. [Key gratuita](https://tavily.com), 1.000 creditos/mes. Sin ella el agente conversa pero no verifica datos de eventos |
| `HXQ_OFFICIAL_SOURCES` | Opcional: dominios confiables del ambito `oficial` |
| `DATABASE_URL` | Postgres (Neon en produccion). Sin ella no hay historial |
| `AZURE_STORAGE_ACCOUNT` / `AZURE_STORAGE_CONTAINER` | Blob Storage para imagenes y adjuntos. Usa Managed Identity, sin claves |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Opcional: telemetria. Los prompts NO se exportan salvo `HXQ_TELEMETRY_SENSITIVE=true` |

**No configures `AZURE_OPENAI_API_VERSION`.** Cada cliente de MAF elige el valor correcto
para su superficie de API; fijarlo produce `400 BadRequest: API version not supported`.
Ver `docs/API-VERIFICADA.md`.

## Que sabe hacer hoy

- Conversar en espanol de Mexico, con la fecha de hoy resuelta y zona horaria de la comunidad
- `buscar_web(query, ambito)`: busqueda via Tavily. El ambito `oficial` restringe a
  pokemongolive.com, LeekDuck y Serebii; `abierto` busca en todo internet
- `consultar_clima(lugar, fecha)`: pronostico via Open-Meteo, horizonte de 16 dias
- Citar la fuente de cada dato de evento, y **negarse a inventar** una fecha si no la verifica
- Controles por chat: tono, canal destino y longitud del copy
- Cada llamada a tool visible como paso colapsable en la interfaz
