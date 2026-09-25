-- Biblioteca de contenido de HXQ.
--
-- Tablas propias, separadas del esquema de Chainlit a proposito: el de Chainlit lo
-- gobierna el upstream y puede cambiar con sus migraciones. Nombres en snake_case para
-- distinguirlas de un vistazo de las "Tablas" PascalCase de Chainlit.
--
-- Guarda cada pieza aprobada para poder reusarla, mantener consistencia de estilo y no
-- repetir una dinamica que ya se hizo. Es el activo que se acumula con el uso.

CREATE TABLE IF NOT EXISTS pieza (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- quedada | anuncio_evento | infografia | dinamica
    tipo            TEXT NOT NULL,
    titulo          TEXT NOT NULL,

    -- Copy por canal: {"whatsapp": "...", "instagram": "...", "campfire": {...}}
    -- JSONB y no columnas fijas porque los canales van a cambiar antes que el esquema.
    contenido       JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Fecha del evento al que corresponde la pieza, no la de creacion. Es la que sirve
    -- para buscar "que publicamos para el Community Day de octubre".
    evento_fecha    DATE,

    -- Key del objeto en Blob Storage. Las imagenes no viven en Postgres.
    imagen_object_key TEXT,

    -- Que pidio el admin. Sirve para rehacer una pieza y para entender que prompts
    -- producen buenos resultados.
    prompt          TEXT,

    creado_por      TEXT NOT NULL,          -- correo del admin
    thread_id       TEXT,                   -- conversacion donde se genero
    aprobada        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS pieza_tipo_idx          ON pieza (tipo);
CREATE INDEX IF NOT EXISTS pieza_creado_en_idx     ON pieza (creado_en DESC);
CREATE INDEX IF NOT EXISTS pieza_evento_fecha_idx  ON pieza (evento_fecha);
CREATE INDEX IF NOT EXISTS pieza_aprobada_idx      ON pieza (aprobada) WHERE aprobada;

-- Busqueda por texto en espanol sobre titulo y prompt, para "ya hicimos algo asi?".
CREATE INDEX IF NOT EXISTS pieza_busqueda_idx ON pieza
    USING GIN (to_tsvector('spanish', coalesce(titulo, '') || ' ' || coalesce(prompt, '')));
