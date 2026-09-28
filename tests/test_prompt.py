"""Carga del system prompt desde `prompt.md`.

El prompt es contenido que edita una persona, no codigo. Estos tests cubren lo que puede
salir mal cuando alguien lo edita: llaves sueltas en el texto, placeholders inventados, o
el archivo directamente ausente.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from hxq_agent.agent import instructions as ins
from hxq_agent.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        hxq_community_name="HuixquiGo",
        hxq_community_city="Huixquilucan",
        hxq_timezone="America/Mexico_City",
    )


class TestLectura:
    def test_el_archivo_existe_junto_al_modulo(self) -> None:
        assert ins.RUTA_PROMPT.is_file(), "prompt.md debe viajar con el paquete"

    def test_tiene_contenido_de_verdad(self) -> None:
        assert len(ins.leer_prompt()) > 1000

    def test_el_comentario_de_cabecera_no_llega_al_modelo(self) -> None:
        """Documenta los placeholders para quien edita, pero gastaria tokens cada turno."""
        assert "<!--" not in ins.leer_prompt()
        assert "Placeholders disponibles" not in ins.leer_prompt()

    def test_si_falta_el_archivo_el_error_es_claro(self, tmp_path) -> None:
        with pytest.raises(ins.PromptNoDisponible, match="system prompt"):
            ins.leer_prompt(tmp_path / "no-existe.md")

    def test_la_version_sale_del_contenido(self, tmp_path) -> None:
        """Derivada y no mantenida a mano: un numero que hay que acordarse de subir
        acaba mintiendo."""
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("uno", encoding="utf-8")
        b.write_text("dos", encoding="utf-8")
        assert ins.version_prompt(a) != ins.version_prompt(b)
        assert ins.version_prompt(a) == ins.version_prompt(a)


class TestSustitucion:
    def test_reemplaza_lo_conocido(self) -> None:
        assert ins.sustituir("hola {{quien}}", {"quien": "mundo"}) == "hola mundo"

    def test_varias_veces_el_mismo(self) -> None:
        assert ins.sustituir("{{x}} y {{x}}", {"x": "a"}) == "a y a"

    def test_una_llave_suelta_no_revienta(self) -> None:
        """El motivo de no usar str.format: el archivo lo edita una persona y puede
        escribir un ejemplo de JSON o una nota entre llaves."""
        texto = 'ejemplo: {"clave": "valor"} y {suelto}'
        assert ins.sustituir(texto, {"x": "a"}) == texto

    def test_un_placeholder_inventado_se_deja_visible(self, caplog) -> None:
        """Mejor un hueco que se ve que un agente que no arranca."""
        salida = ins.sustituir("hola {{inventado}}", {"x": "a"})
        assert salida == "hola {{inventado}}"

    def test_avisa_de_los_placeholders_inventados(self, caplog) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            ins.sustituir("{{inventado}}", {})
        assert "inventado" in caplog.text


class TestBuildInstructions:
    def test_sustituye_el_contexto_de_la_comunidad(self, settings: Settings) -> None:
        out = ins.build_instructions(settings)
        assert "HuixquiGo" in out
        assert "Huixquilucan" in out
        assert "{{" not in out, "no debe quedar ningun placeholder sin sustituir"

    def test_inyecta_la_fecha_resuelta(self, settings: Settings) -> None:
        out = ins.build_instructions(settings, now=datetime(2026, 10, 1, 20, 0))
        assert "01/10/2026" in out
        assert "jueves" in out

    def test_los_dias_llevan_tilde(self) -> None:
        assert "miércoles" in ins._DIAS
        assert "sábado" in ins._DIAS

    def test_un_datetime_naive_es_hora_de_la_comunidad(self, settings: Settings) -> None:
        """23:30 del 1/10 en Mexico no debe convertirse en el dia 2 por la tz del servidor."""
        out = ins.build_instructions(settings, now=datetime(2026, 10, 1, 23, 30))
        assert "01/10/2026" in out

    @pytest.mark.parametrize(
        "regla",
        [
            "NUNCA inventes",
            "PREGUNTALO",
            "Tu no publicas nada",
            "no tiene API publica",
            "infografia_incursion",
        ],
    )
    def test_las_reglas_duras_siguen_en_el_prompt(self, settings: Settings, regla: str) -> None:
        """Si alguien edita prompt.md y se lleva una por delante, esto lo caza."""
        assert regla in ins.build_instructions(settings)


class TestInventarioDeTools:
    """El prompt decia "Tienes dos" cuando ya habia siete.

    La seccion de herramientas va por detras del codigo en cuanto se anade una tool, y el
    sintoma es silencioso: el agente simplemente no usa lo que no sabe que tiene.
    """

    def test_todas_las_tools_registradas_estan_en_el_prompt(self, settings: Settings) -> None:
        from hxq_agent.agent.tools import build_tools

        prompt = ins.build_instructions(settings)
        faltan = [t.name for t in build_tools() if t.name not in prompt]
        assert not faltan, (
            f"Estas tools existen pero el prompt no las menciona: {faltan}. "
            "El agente no usara lo que no sabe que tiene."
        )

    def test_el_prompt_no_menciona_tools_que_no_existen(self, settings: Settings) -> None:
        """El error inverso: una tool que se quito y sigue documentada."""
        import re

        from hxq_agent.agent.tools import build_tools

        reales = {t.name for t in build_tools()}
        prompt = ins.build_instructions(settings)
        # Nombres en backticks con parentesis: asi se escriben las tools en el prompt.
        citadas = set(re.findall(r"`(\w+)\(", prompt))
        fantasmas = citadas - reales
        assert not fantasmas, f"El prompt documenta tools que ya no existen: {fantasmas}"

    def test_la_cuenta_declarada_coincide(self, settings: Settings) -> None:
        """Si el prompt dice un numero de tools, que sea el correcto."""
        import re

        from hxq_agent.agent.tools import build_tools

        numeros = {
            "una": 1,
            "dos": 2,
            "tres": 3,
            "cuatro": 4,
            "cinco": 5,
            "seis": 6,
            "siete": 7,
            "ocho": 8,
            "nueve": 9,
            "diez": 10,
        }
        prompt = ins.build_instructions(settings)
        m = re.search(r"Tienes (\w+)\.", prompt)
        if m and m.group(1).lower() in numeros:
            assert numeros[m.group(1).lower()] == len(build_tools()), (
                f"El prompt dice 'Tienes {m.group(1)}' y hay {len(build_tools())} tools."
            )
