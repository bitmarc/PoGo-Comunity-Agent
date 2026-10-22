-- Datos propios de la comunidad: puntos de reunion, codigos de jugadores, redes, historia.
--
-- Una sola tabla con JSONB y no una por tema, a proposito: el esquema de cada tema vive
-- en `schemas/comunidad.py` (Pydantic) y se valida ahi antes de escribir. Asi agregar un
-- tema o un campo es cambiar codigo, no migrar una tabla, que es justo lo que
-- `apply_schema.py` no sabe hacer.
--
-- `nombre` es la clave natural dentro del tema (el nombre del punto, el alias del
-- jugador, la red social, el titulo de la historia). Es lo que el admin dice en el chat.

CREATE TABLE IF NOT EXISTS dato_comunidad (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- puntos_reunion | codigos_jugadores | redes_sociales | historia
    tema            TEXT NOT NULL,
    nombre          TEXT NOT NULL,

    -- El registro validado completo, clave incluida.
    datos           JSONB NOT NULL DEFAULT '{}'::jsonb,

    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_por TEXT NOT NULL,          -- correo del admin que confirmo el cambio

    -- Borrado logico: un dato borrado por error se recupera volviendo a guardarlo.
    eliminado_en    TIMESTAMPTZ
);

-- No parcial a proposito: volver a guardar un nombre borrado lo restaura en vez de
-- duplicarlo, y la semilla con ON CONFLICT DO NOTHING no resucita lo que se borro.
CREATE UNIQUE INDEX IF NOT EXISTS dato_comunidad_clave_idx
    ON dato_comunidad (tema, lower(nombre));
