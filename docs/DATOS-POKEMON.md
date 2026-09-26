# Fuentes de datos de Pokémon

Evaluadas en vivo el 26 de septiembre de 2026, con peticiones puntuales (sin crawling).

## PokéAPI — implementado

| | |
|---|---|
| Base | `https://pokeapi.co/api/v2` |
| Arte | `raw.githubusercontent.com/PokeAPI/sprites/.../official-artwork/{id}.png` |
| Auth | Ninguna |
| Da | Arte oficial **512×512 con canal alfa**, tipos, nombre en español |
| Tamaño | ~14 KB por especie, ~120 KB por imagen |
| Condiciones | Piden cachear en lugar de repetir consultas e identificar el cliente |

Es la fuente del arte central de las piezas. El canal alfa es lo que permite montar el
Pokémon sobre el fondo neón sin un recuadro visible.

Y hace algo que no es obvio: como trae los **tipos reales**, los acentos de la pieza
salen del Pokémon y no de lo que el modelo crea recordar. Cottonee sale verde y rosa
porque PokéAPI dice `grass`/`fairy`, no porque nadie lo escribiera.

Implementado en `brand/pokemon.py`, con caché en disco que no caduca: el arte oficial de
un Pokémon no cambia.

**Por qué esto y no generar el Pokémon con IA:** Azure rechaza generar propiedad
intelectual (`moderation_blocked`, ver `API-VERIFICADA.md` #23). Y aunque no lo hiciera,
un Pokémon dibujado por IA se nota y no es el que la gente espera ver.

## Pokébattler — evaluado, NO implementado

| | |
|---|---|
| Base | `https://fight.pokebattler.com` |
| Auth | Ninguna para HTTP |
| Da | Rotación de incursiones, counters rankeados con movimientos, PC de jefe, simulaciones |
| MCP | `https://mcp.pokebattler.com/mcp` — respuestas de 1–5 KB, exige cuenta gratuita |

Probado en vivo y funciona:

- `GET /raids` → 680 KB, 66 tiers. Devolvió la rotación real (Xerneas en nivel 5,
  Malamar y Victreebel en mega).
- `GET /raids/defenders/{jefe}/levels/RAID_LEVEL_5/attackers/levels/40/strategies/...`
  → **1.7 MB**, 30 atacantes rankeados con sus movimientos rápido y cargado.

### Condiciones de uso

1. **Atribución obligatoria** al publicar resultados derivados de sus datos. Eso es un
   requisito de diseño sobre la plantilla: tiene que llevar una línea "Datos: Pokébattler".
2. **Caché agresiva.** Piden no repetir consultas; las de ranking las califican de caras.
3. **Identificar el cliente** por `User-Agent`.
4. **No recorrer** el espacio combinatorio atacante × defensor × moveset.
5. Carga automatizada sostenida puede ser limitada. Para volumen alto, contactarlos.
6. Es un proyecto de fans, sin relación con Niantic, Nintendo ni The Pokémon Company.

Nada de esto impide el uso que nos interesa: unas pocas consultas al mes, cacheadas.

### Por qué no ahora

No es por las condiciones, que son razonables. Es por dónde está el valor:

1. **La Fase 4 es la prioridad declarada.** El paquete completo de quedada (copy por
   canal + imagen + `.ics`) es lo que ahorra ~45 min por quedada. Las infografías de
   evento oficial son otro trabajo distinto.
2. **El coste real está en el mapeo, no en la API.** Pokébattler devuelve
   `ZAMAZENTA_CROWNED_SHIELD_FORM` y `METAL_CLAW_FAST`; hay que traducir eso a ids de
   PokéAPI para el sprite, y a nombres de movimiento en español. Ese diccionario es el
   grueso del trabajo y no se prueba con dos llamadas.
3. **Es la plantilla más rica del proyecto.** Las infografías reales llevan counters con
   sprites, debilidades, PC de jefe normal y potenciado, megas recomendadas y notas. Se
   construye mejor sobre un motor ya rodado que sobre uno recién escrito.

### Cuando toque, empezar por el MCP

El servidor MCP devuelve **1–5 KB** en vez de 1.7 MB, y Microsoft Agent Framework soporta
MCP de forma nativa (`MCPStreamableHTTPTool`). Eso evita meter un parser de 1.7 MB en el
proyecto y deja que el modelo consulte lo que necesite. El precio es una cuenta gratuita
de Pokébattler y una dependencia de su servidor.

Conviene medir las dos rutas antes de decidir: HTTP crudo con caché propia es más
predecible; MCP es mucho más barato en tokens y en código.
