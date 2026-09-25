"""Los controles por chat se traducen a instrucciones que el modelo entienda."""

from __future__ import annotations

from hxq_agent.ui.settings import (
    CANALES,
    LONGITUDES,
    PREFERENCIAS_POR_DEFECTO,
    TONOS,
    describir_preferencias,
)


class TestDescribirPreferencias:
    def test_los_defaults_no_anaden_ruido_al_prompt(self) -> None:
        """Si nada cambio, no se gastan tokens en repetir lo obvio."""
        assert describir_preferencias(PREFERENCIAS_POR_DEFECTO) == ""

    def test_diccionario_vacio_tampoco(self) -> None:
        assert describir_preferencias({}) == ""

    def test_tono_informal(self) -> None:
        salida = describir_preferencias({**PREFERENCIAS_POR_DEFECTO, "tono": TONOS[1]})
        assert "informal" in salida

    def test_tono_neutro_apaga_emojis(self) -> None:
        salida = describir_preferencias({**PREFERENCIAS_POR_DEFECTO, "tono": TONOS[2]})
        assert "sin emojis" in salida

    def test_canal_unico_acota_la_salida(self) -> None:
        salida = describir_preferencias({**PREFERENCIAS_POR_DEFECTO, "canal": CANALES[1]})
        assert "solo el bloque de WhatsApp" in salida

    def test_combina_varias_preferencias(self) -> None:
        salida = describir_preferencias(
            {"tono": TONOS[2], "canal": CANALES[1], "longitud": LONGITUDES[1]}
        )
        assert "sin emojis" in salida
        assert "WhatsApp" in salida
        assert "breve" in salida

    def test_preferencia_desconocida_no_revienta(self) -> None:
        describir_preferencias({"tono": "algo que no existe", "canal": "otro"})
