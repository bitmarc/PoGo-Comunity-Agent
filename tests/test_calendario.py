"""Generacion del archivo .ics.

El valor aqui es la zona horaria y los limites: un evento que se agenda seis horas tarde
porque el contenedor corre en UTC es peor que no tener calendario.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from hxq_agent.agent.tools import calendario as cal

MX = ZoneInfo("America/Mexico_City")


async def _llamar(**kwargs) -> str:
    res = await cal.crear_ics.invoke(arguments=kwargs)
    if isinstance(res, list):
        return "\n".join(c.text or "" for c in res)
    return str(res)


class TestNombreArchivo:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("Quedada de Incursiones", "quedada-de-incursiones"),
            ("Día de la Comunidad", "dia-de-la-comunidad"),
            ("¡¡¡ Raid !!!", "raid"),
            ("", "quedada"),
            ("///", "quedada"),
        ],
    )
    def test_casos(self, entrada: str, esperado: str) -> None:
        assert cal.nombre_archivo(entrada) == esperado


class TestConstruirIcs:
    def _ics(self, **extra) -> str:
        base = {
            "titulo": "Quedada de Incursiones",
            "lugar": "Parque Metropolitano, Zapopan",
            "inicio": datetime(2026, 10, 3, 18, 0, tzinfo=MX),
            "fin": datetime(2026, 10, 3, 20, 30, tzinfo=MX),
        }
        return cal.construir_ics(**{**base, **extra}).decode("utf-8")

    def test_es_un_calendario_valido(self) -> None:
        ics = self._ics()
        assert ics.startswith("BEGIN:VCALENDAR")
        assert "END:VCALENDAR" in ics
        # PRODID es obligatorio en RFC 5545; sin el algunos clientes lo rechazan.
        assert "PRODID" in ics
        assert "VERSION:2.0" in ics

    def test_lleva_los_datos(self) -> None:
        ics = self._ics()
        assert "Quedada de Incursiones" in ics
        assert "Zapopan" in ics

    def test_cada_evento_tiene_uid_propio(self) -> None:
        """Sin UID unico, importar dos quedadas puede sobrescribir una."""
        a, b = self._ics(), self._ics()
        uid_a = [x for x in a.splitlines() if x.startswith("UID:")][0]
        uid_b = [x for x in b.splitlines() if x.startswith("UID:")][0]
        assert uid_a != uid_b

    def test_se_puede_volver_a_parsear(self) -> None:
        """La prueba real: que un cliente de calendario pueda leerlo."""
        from icalendar import Calendar

        c = Calendar.from_ical(self._ics())
        ev = c.walk("VEVENT")[0]
        assert str(ev["SUMMARY"]) == "Quedada de Incursiones"
        assert ev["DTSTART"].dt == datetime(2026, 10, 3, 18, 0, tzinfo=MX)
        assert ev["DTEND"].dt - ev["DTSTART"].dt == timedelta(hours=2, minutes=30)


class TestTool:
    async def test_caso_normal(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HXQ_DATA_DIR", str(tmp_path))
        salida = await _llamar(
            titulo="Quedada",
            lugar="Parque",
            fecha="2026-10-03",
            hora_inicio="18:00",
            hora_fin="20:30",
        )
        assert ".ics" in salida
        assert list((tmp_path / "calendario").glob("*.ics"))

    async def test_sin_hora_de_fin_asume_dos_horas(self, tmp_path, monkeypatch) -> None:
        from icalendar import Calendar

        monkeypatch.setenv("HXQ_DATA_DIR", str(tmp_path))
        await _llamar(titulo="Q", lugar="P", fecha="2026-10-03", hora_inicio="18:00")
        c = Calendar.from_ical(next((tmp_path / "calendario").glob("*.ics")).read_bytes())
        ev = c.walk("VEVENT")[0]
        assert ev["DTEND"].dt - ev["DTSTART"].dt == cal.DURACION_POR_DEFECTO

    async def test_usa_la_zona_horaria_de_la_comunidad(self, tmp_path, monkeypatch) -> None:
        """No la del servidor: un contenedor en UTC agendaria seis horas tarde."""
        from icalendar import Calendar

        monkeypatch.setenv("HXQ_DATA_DIR", str(tmp_path))
        await _llamar(titulo="Q", lugar="P", fecha="2026-10-03", hora_inicio="18:00")
        c = Calendar.from_ical(next((tmp_path / "calendario").glob("*.ics")).read_bytes())
        inicio = c.walk("VEVENT")[0]["DTSTART"].dt
        assert inicio.utcoffset() == datetime(2026, 10, 3, 18, 0, tzinfo=MX).utcoffset()
        assert inicio.hour == 18

    async def test_cruzar_medianoche_no_da_duracion_negativa(self, tmp_path, monkeypatch) -> None:
        from icalendar import Calendar

        monkeypatch.setenv("HXQ_DATA_DIR", str(tmp_path))
        await _llamar(
            titulo="Q", lugar="P", fecha="2026-10-03", hora_inicio="23:00", hora_fin="01:00"
        )
        c = Calendar.from_ical(next((tmp_path / "calendario").glob("*.ics")).read_bytes())
        ev = c.walk("VEVENT")[0]
        assert ev["DTEND"].dt > ev["DTSTART"].dt
        assert ev["DTEND"].dt - ev["DTSTART"].dt == timedelta(hours=2)

    @pytest.mark.parametrize("fecha", ["03/10/2026", "el sabado", "2026-13-45", ""])
    async def test_fecha_invalida_da_un_error_accionable(self, fecha: str) -> None:
        salida = await _llamar(titulo="Q", lugar="P", fecha=fecha, hora_inicio="18:00")
        assert "aaaa-mm-dd" in salida

    @pytest.mark.parametrize("hora", ["6pm", "25:00", "tarde", ""])
    async def test_hora_invalida_da_un_error_accionable(self, hora: str) -> None:
        salida = await _llamar(titulo="Q", lugar="P", fecha="2026-10-03", hora_inicio=hora)
        assert "HH:MM" in salida
