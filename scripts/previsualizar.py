"""Renderiza piezas de ejemplo a `out/` para revisarlas a ojo.

El motor valida datos y evita desbordes, pero si una pieza "se ve de la comunidad" solo
lo dice un humano mirandola. Esto hace ese bucle rapido.

Uso:
    ./.venv/Scripts/python.exe scripts/previsualizar.py
    ./.venv/Scripts/python.exe scripts/previsualizar.py quedada
"""

from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from hxq_agent.brand.render import renderizar_sync  # noqa: E402
from hxq_agent.schemas.piezas import AnuncioEvento, Quedada  # noqa: E402

SALIDA = RAIZ / "out"


def contexto(pieza) -> dict:
    """Aplana el modelo mas sus propiedades calculadas para la plantilla."""
    ctx = pieza.model_dump()
    ctx.update(
        {
            "acento_1": pieza.acentos[0],
            "acento_2": pieza.acentos[1],
            "escala_titulo": pieza.escala_titulo,
            "escala_subtitulo": pieza.escala_subtitulo,
            "fecha_texto": pieza.fecha_texto,
            "horario_texto": pieza.horario_texto,
        }
    )
    return ctx


EJEMPLOS: dict[str, object] = {
    "quedada": Quedada(
        titulo="Quedada de Incursiones",
        subtitulo="Vamos por Rayquaza en raids de 5 estrellas",
        lugar="Parque Metropolitano, Zapopan",
        fecha=date(2026, 10, 3),
        hora_inicio=time(18, 0),
        hora_fin=time(20, 30),
        detalles=["Trae pases de incursión", "Llegar 10 min antes", "Grupo de WhatsApp"],
    ),
    # Con tipos: los acentos deben salir verde y rosa, como la pieza de Cottonee.
    "quedada_tipos": Quedada(
        titulo="Día de la Comunidad",
        subtitulo="Cottonee protagoniza el evento",
        lugar="Plaza Principal, Huixquilucan",
        fecha=date(2026, 11, 14),
        hora_inicio=time(14, 0),
        hora_fin=time(17, 0),
        tipos=["planta", "hada"],
        detalles=["Triple PX por captura", "Incienso de 3 horas"],
    ),
    "anuncio_evento": AnuncioEvento(
        titulo="Hora Legendaria",
        subtitulo="Groudon en incursiones de 5 estrellas",
        fecha_inicio=date(2026, 10, 15),
        hora_inicio=time(18, 0),
        hora_fin=time(19, 0),
        tipos=["tierra"],
        bonus=[
            "Más incursiones activas en gimnasios",
            "Mayor probabilidad de variocolor",
            "Potenciado por clima soleado",
        ],
    ),
    # Caso limite: los textos mas largos que permite el esquema.
    "quedada_larga": Quedada(
        titulo="Quedada de Incursiones y Capturas Comunitaria",
        subtitulo="Recorrido por el centro con paradas en gimnasios y poképaradas",
        lugar="Explanada del Centro Cultural Huixquilucan Poniente",
        fecha=date(2026, 12, 20),
        hora_inicio=time(9, 30),
        hora_fin=time(13, 0),
        detalles=[
            "Trae pases de incursión remota y presencial",
            "Habrá módulos cebo en todas las paradas",
            "Punto de reunión junto a la fuente",
            "Llegar diez minutos antes de la hora",
        ],
    ),
}


def main() -> None:
    pedidos = sys.argv[1:] or list(EJEMPLOS)
    SALIDA.mkdir(exist_ok=True)

    for nombre in pedidos:
        pieza = EJEMPLOS.get(nombre)
        if pieza is None:
            print(f"  ? {nombre}: no existe. Disponibles: {', '.join(EJEMPLOS)}")
            continue
        png = renderizar_sync(pieza.plantilla, contexto(pieza))
        destino = SALIDA / f"{nombre}.png"
        destino.write_bytes(png)
        print(f"  {destino.relative_to(RAIZ)}  ({len(png) // 1024} KB)")


if __name__ == "__main__":
    main()
