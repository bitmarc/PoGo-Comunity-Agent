-- Datos iniciales de la comunidad, tomados de las notas de los admins.
--
-- ON CONFLICT DO NOTHING: reaplicar no pisa lo que se edito desde el chat ni resucita lo
-- que se borro. A partir de aqui, los cambios se hacen con el agente, no en este archivo.
--
-- jsonb_build_object y no literales JSON: el texto lleva comillas dobles y escaparlas
-- a mano dentro de SQL es pedir un error.

INSERT INTO dato_comunidad (tema, nombre, datos, actualizado_por) VALUES
('puntos_reunion', 'Palacio Municipal', jsonb_build_object(
    'nombre', 'Palacio Municipal', 'sede', true, 'concurrencia', 'alta',
    'variantes', jsonb_build_array('explanada', 'presidencia', 'palacio', 'quiosco'),
    'latitud', 19.3601509, 'longitud', -99.351957, 'zona', 'centro'), 'semilla'),
('puntos_reunion', 'Jardín', jsonb_build_object(
    'nombre', 'Jardín', 'sede', false, 'concurrencia', 'alta',
    'variantes', jsonb_build_array('jardin de la cultura'),
    'latitud', 19.357882, 'longitud', -99.341181, 'zona', 'san juan'), 'semilla'),
('puntos_reunion', 'San Antonio', jsonb_build_object(
    'nombre', 'San Antonio', 'sede', false, 'concurrencia', 'media',
    'variantes', jsonb_build_array('iglesia de san antonio', 'ruta 15'),
    'latitud', 19.361800, 'longitud', -99.351700, 'zona', 'centro'), 'semilla'),
('puntos_reunion', 'Monte Pío', jsonb_build_object(
    'nombre', 'Monte Pío', 'sede', false, 'concurrencia', 'media',
    'variantes', jsonb_build_array('michoacana', 'ruta 85', 'pasteleria', 'la 85'),
    'latitud', 19.361202, 'longitud', -99.3502935, 'zona', 'centro'), 'semilla'),
('puntos_reunion', 'Deportivo de San Martín', jsonb_build_object(
    'nombre', 'Deportivo de San Martín', 'sede', false, 'concurrencia', 'media',
    'variantes', jsonb_build_array('cancha de san martin', 'deportivo san martin'),
    'latitud', 19.358391, 'longitud', -99.353408, 'zona', 'san martin'), 'semilla'),
('puntos_reunion', 'Iglesia de San Martín', jsonb_build_object(
    'nombre', 'Iglesia de San Martín', 'sede', false, 'concurrencia', 'baja',
    'variantes', jsonb_build_array('san martin'),
    'latitud', 19.358391, 'longitud', -99.353408, 'zona', 'san martin'), 'semilla'),

('redes_sociales', 'instagram', jsonb_build_object(
    'red', 'instagram', 'nombre', 'huixquigo',
    'url', 'https://www.instagram.com/huixquigo/'), 'semilla'),

('historia', 'Orígenes', jsonb_build_object(
    'titulo', 'Orígenes',
    'tema', 'Cómo y cuándo se fundó la comunidad',
    'detalle', 'La comunidad de Pokémon GO de Huixquilucan se remonta a 2022, con el '
        'nombre de Poke-Huixqui, que evolucionó a HuixquiGo en 2025. Su fundador es '
        'desconocido; actualmente la administración reside en manos de "Masiosare", '
        'administrador principal. El logo de la comunidad está inspirado en la naturaleza '
        'de Huixquilucan, con Venusaur Gigamax.'), 'semilla')
ON CONFLICT DO NOTHING;
