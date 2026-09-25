# HXQ Agent

Agente copiloto de comunicacion para los administradores de una comunidad local de Pokemon GO
(Mexico). Genera paquetes de contenido listos para publicar: copy por canal, imagen con el
branding de la comunidad y archivo de calendario.

Stack: Microsoft Agent Framework 1.x + Chainlit, desplegado en Azure Container Apps.
Plan completo por fases en [`docs/PLAN.md`](docs/PLAN.md).
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

## Configuracion requerida

| Variable | Para que |
|---|---|
| `OAUTH_GOOGLE_CLIENT_ID` / `_SECRET` | Login con Google. Redirect URI: `http://localhost:8000/auth/oauth/google/callback` |
| `CHAINLIT_AUTH_SECRET` | Firma de la sesion |
| `HXQ_ADMIN_EMAILS` | Allowlist de correos, separados por coma. Vacia = nadie entra |
| `AZURE_OPENAI_ENDPOINT` | Recurso de Azure OpenAI |
| `AZURE_OPENAI_API_KEY` | Opcional: si se omite se usa `DefaultAzureCredential` (Managed Identity / `az login`) |
