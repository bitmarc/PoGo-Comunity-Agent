"""Datos propios de la comunidad: consultarlos y proponer cambios.

Dos tools y no una por tema: el tema es un parametro cerrado y el esquema de cada uno se
valida con Pydantic. Ocho tools casi iguales gastarian tokens de esquema en cada turno y
le darian al modelo mas ocasiones de elegir la equivocada.

Escribir NO es inmediato. `proponer_cambio_comunidad` valida y deja el cambio pendiente;
lo aplica el admin con un boton. Un punto de reunion con la coordenada mal entendida
acabaria en el aviso de la siguiente quedada.

Este modulo no importa Chainlit: el boton lo pone `ui/cambios.py`, que recoge el cambio
pendiente con `tomar_cambio`.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from agent_framework import tool
from pydantic import Field, ValidationError

from hxq_agent.schemas.comunidad import TEMAS, TemaId, buscar_en, normalizar
from hxq_agent.storage import comunidad as almacen
from hxq_agent.storage.comunidad import ComunidadNoDisponible

logger = logging.getLogger(__name__)

_NOMBRES_TEMA = {
    "puntos_reunion": "puntos de reunion",
    "codigos_jugadores": "codigos de jugadores",
    "redes_sociales": "redes sociales",
    "historia": "historia de la comunidad",
}

AVISO_PRIVADO = (
    "Uso interno: estos codigos son solo para el admin. No los incluyas en contenido "
    "para publicar (WhatsApp, Instagram, Campfire, piezas)."
)

# Marca que la UI busca en la salida de la tool para poner el boton.
MARCA_PENDIENTE = "Cambio pendiente de confirmar:"
_PATRON_PENDIENTE = re.compile(re.escape(MARCA_PENDIENTE) + r" ([0-9a-f]{12})")


# ---------- Consulta ----------


def _formatear(tema: str, fila: dict[str, Any]) -> str:
    """Un registro en markdown legible para el modelo."""
    try:
        r = TEMAS[tema].modelo.model_validate(fila)
    except ValidationError:
        # Un registro que ya no cumple el esquema (se cambio un campo despues de
        # guardarlo) se muestra crudo antes que esconderlo.
        return json.dumps(fila, ensure_ascii=False)

    if tema == "puntos_reunion":
        lineas = [f"## {r.nombre}{' (sede)' if r.sede else ''}"]
        lineas.append(f"Zona: {r.zona} · Concurrencia: {r.concurrencia}")
        if r.variantes:
            lineas.append(f"Tambien le dicen: {', '.join(r.variantes)}")
        lineas.append(f"Coordenadas: {r.coordenadas} · Maps: {r.maps_url}")
        return "\n".join(lineas)
    if tema == "codigos_jugadores":
        return f"- {r.alias} ({r.nombre_jugador}, {r.equipo}): {r.codigo_legible}"
    if tema == "redes_sociales":
        return f"- {r.red}: {r.nombre} — {r.url}"
    return f"## {r.titulo}\n_{r.tema}_\n\n{r.detalle}"


@tool
async def consultar_comunidad(
    tema: Annotated[
        TemaId,
        Field(
            description=(
                "Que consultar: 'puntos_reunion' (lugares donde quedamos, con apodos y "
                "coordenadas), 'codigos_jugadores' (codigos de entrenador de miembros), "
                "'redes_sociales' (cuentas oficiales) o 'historia' (origen y momentos de "
                "la comunidad)."
            )
        ),
    ],
    busqueda: Annotated[
        str,
        Field(
            description=(
                "Texto para filtrar, sin importar acentos: un lugar como lo dijo el admin "
                "('el quiosco'), un alias, una zona. Vacio para ver todo el tema."
            )
        ),
    ] = "",
) -> str:
    """Consulta los datos propios de la comunidad guardados por los admins.

    Usala para cualquier pregunta sobre la comunidad (donde quedamos, como se llama
    nuestra cuenta, desde cuando existimos, el codigo de alguien) y antes de armar una
    quedada, para resolver el lugar al punto de reunion oficial con sus coordenadas.
    """
    if tema not in TEMAS:
        return f"Tema desconocido: {tema!r}. Opciones: {', '.join(TEMAS)}."

    try:
        filas = await almacen.listar(tema)
    except ComunidadNoDisponible as exc:
        return f"Los datos de la comunidad no estan disponibles: {exc}"
    except Exception as exc:
        logger.exception("Fallo al consultar datos de la comunidad")
        return f"No pude consultar los datos de la comunidad: {exc}"

    nombre_tema = _NOMBRES_TEMA[tema]
    if not filas:
        return (
            f"No hay {nombre_tema} registrados todavia. Si el admin te los da, propon "
            "guardarlos con `proponer_cambio_comunidad`."
        )

    encontradas = buscar_en(filas, busqueda)
    if not encontradas:
        extra = " Usa el lugar tal cual lo dijo el admin." if tema == "puntos_reunion" else ""
        return f"Nada en {nombre_tema} coincide con {busqueda!r}.{extra}"

    separador = "\n\n" if tema in ("puntos_reunion", "historia") else "\n"
    salida = f"{len(encontradas)} registro(s) de {nombre_tema}:\n\n" + separador.join(
        _formatear(tema, f) for f in encontradas
    )
    if TEMAS[tema].privado:
        salida += f"\n\n{AVISO_PRIVADO}"
    return salida


# ---------- Cambios ----------


@dataclass
class Cambio:
    """Un cambio validado, listo para que el admin lo confirme."""

    tema: str
    operacion: Literal["guardar", "eliminar"]
    # Clave del registro tal como esta guardado; None si es nuevo.
    nombre_actual: str | None
    antes: dict[str, Any] | None
    despues: dict[str, Any] | None

    @property
    def nombre(self) -> str:
        """Clave con la que queda el registro."""
        if self.despues is not None:
            return str(self.despues[TEMAS[self.tema].clave])
        return self.nombre_actual or ""

    def resumen(self) -> str:
        """Lo que se le enseña al admin junto al boton: que cambia, campo a campo."""
        tema = _NOMBRES_TEMA[self.tema]
        if self.operacion == "eliminar":
            return f"Eliminar **{self.nombre}** de {tema}."
        if self.antes is None:
            campos = "\n".join(f"- {k}: {_valor(v)}" for k, v in (self.despues or {}).items())
            return f"Agregar **{self.nombre}** a {tema}:\n{campos}"
        cambios = [
            f"- {k}: {_valor(self.antes.get(k))} → {_valor(v)}"
            for k, v in (self.despues or {}).items()
            if self.antes.get(k) != v
        ]
        return f"Actualizar **{self.nombre_actual}** en {tema}:\n" + "\n".join(cambios)


def _valor(v: Any) -> str:
    if v is None:
        return "(vacio)"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "(ninguna)"
    if isinstance(v, bool):
        return "si" if v else "no"
    return str(v)


def _explicar_errores(exc: ValidationError) -> str:
    return "\n".join(
        f"- {'.'.join(str(x) for x in e['loc']) or '(raiz)'}: {e['msg']}" for e in exc.errors()
    )


async def preparar_cambio(tema: str, operacion: str, nombre: str, datos: str = "") -> Cambio | str:
    """Valida un cambio contra lo guardado. Devuelve el `Cambio` o el texto del problema.

    En `guardar` sobre un registro existente, `datos` se mezcla con lo guardado: para
    cambiar la zona de un punto basta con mandar la zona.
    """
    if tema not in TEMAS:
        return f"Tema desconocido: {tema!r}. Opciones: {', '.join(TEMAS)}."
    if operacion not in ("guardar", "eliminar"):
        return f"Operacion desconocida: {operacion!r}. Usa 'guardar' o 'eliminar'."
    if not nombre.strip():
        return "Falta `nombre`: el registro que se crea, cambia o elimina."

    definicion = TEMAS[tema]
    actual = await almacen.obtener(tema, nombre)

    if operacion == "eliminar":
        if actual is None:
            return f"No hay nada llamado {nombre!r} en {_NOMBRES_TEMA[tema]}. No hay que borrar."
        return Cambio(tema, "eliminar", str(actual[definicion.clave]), actual, None)

    try:
        nuevos = json.loads(datos) if datos.strip() else {}
    except json.JSONDecodeError as exc:
        return f"`datos` no es un JSON valido ({exc.msg}). Manda un objeto con los campos."
    if not isinstance(nuevos, dict):
        return "`datos` debe ser un objeto JSON con los campos, no una lista ni un valor suelto."

    base = dict(actual) if actual else {definicion.clave: nombre.strip()}
    try:
        registro = definicion.modelo.model_validate({**base, **nuevos})
    except ValidationError as exc:
        accion = "actualizar" if actual else "crear"
        return f"No se puede {accion} {nombre!r}, revisa estos campos:\n{_explicar_errores(exc)}"

    despues = registro.model_dump(mode="json")
    if actual is not None and despues == actual:
        return f"{nombre!r} ya tiene exactamente esos datos. No hay nada que cambiar."

    nuevo_nombre = str(despues[definicion.clave])
    renombra = normalizar(nuevo_nombre) != normalizar(nombre)
    if renombra and await almacen.obtener(tema, nuevo_nombre) is not None:
        return (
            f"Ya existe {nuevo_nombre!r} en {_NOMBRES_TEMA[tema]}. Para cambiarlo, "
            "usa ese nombre; no se puede renombrar encima de otro registro."
        )

    nombre_actual = str(actual[definicion.clave]) if actual else None
    return Cambio(tema, "guardar", nombre_actual, actual, despues)


# Cambios validados que esperan a que la UI ponga el boton. Por id aleatorio, asi que
# dos admins a la vez no se pisan; `tomar_cambio` los saca al recogerlos.
_PENDIENTES: dict[str, Cambio] = {}


def tomar_cambio(salida_tool: str) -> Cambio | None:
    """El cambio que anuncia la salida de `proponer_cambio_comunidad`, si lo hay."""
    m = _PATRON_PENDIENTE.search(salida_tool)
    return _PENDIENTES.pop(m.group(1), None) if m else None


@tool
async def proponer_cambio_comunidad(
    tema: Annotated[
        TemaId,
        Field(description="Tema del dato: el mismo que en `consultar_comunidad`."),
    ],
    operacion: Annotated[
        Literal["guardar", "eliminar"],
        Field(description="'guardar' para crear o modificar, 'eliminar' para borrar."),
    ],
    nombre: Annotated[
        str,
        Field(
            description=(
                "El registro afectado: nombre del punto, alias del jugador, red social "
                "o titulo de la historia. Si ya existe, se modifica ese."
            )
        ),
    ],
    datos: Annotated[
        str,
        Field(
            description=(
                "Solo para 'guardar': objeto JSON con los campos. Si el registro ya existe "
                "manda SOLO lo que cambia; si es nuevo, todos los campos. Vacio al eliminar."
            )
        ),
    ] = "",
) -> str:
    """Propone agregar, modificar o eliminar un dato de la comunidad.

    No escribe nada: valida el cambio y le muestra al admin un boton para confirmarlo.
    Campos por tema: puntos_reunion {nombre, sede, concurrencia: alta|media|baja,
    variantes: [..], latitud, longitud, zona}; codigos_jugadores {alias, nombre_jugador,
    codigo (12 digitos), equipo: instinct|mystic|valor}; redes_sociales {red, nombre,
    url}; historia {titulo, tema, detalle}.
    """
    try:
        cambio = await preparar_cambio(tema, operacion, nombre, datos)
    except ComunidadNoDisponible as exc:
        return f"No se pueden cambiar datos de la comunidad: {exc}"
    except Exception as exc:
        logger.exception("Fallo al preparar un cambio de datos de la comunidad")
        return f"No pude preparar el cambio: {exc}"

    if isinstance(cambio, str):
        return cambio

    cambio_id = uuid.uuid4().hex[:12]
    _PENDIENTES[cambio_id] = cambio
    return (
        f"{MARCA_PENDIENTE} {cambio_id}\n\n{cambio.resumen()}\n\n"
        "El admin ya ve un boton para confirmarlo o cancelarlo. NO digas que se guardo: "
        "todavia no se ha escrito nada. Dile en una linea que lo confirme con el boton."
    )
