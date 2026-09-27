"""Datos de incursion: calculo de PC, formas y traduccion.

El calculo de PC esta verificado contra una infografia REAL de la comunidad: la de
Groudon publicada muestra 2260-2351 normal y 2825-2939 potenciado, y son exactamente los
numeros que sale de esta formula. Si alguien la toca y rompe eso, este test lo caza.
"""

from __future__ import annotations

import pytest

from hxq_agent.brand import pokebattler as pb
from hxq_agent.brand import traduccion as tr

# Stats de Pokemon GO tal como las devuelve Pokebattler.
GROUDON = {"baseAttack": 270, "baseDefense": 228, "baseStamina": 205}
XERNEAS = {"baseAttack": 250, "baseDefense": 185, "baseStamina": 246}


class TestCalculoDePC:
    def test_groudon_coincide_con_la_pieza_publicada(self) -> None:
        """Los cuatro numeros de la infografia real de la comunidad."""
        assert pb.rango_captura(GROUDON, 20) == (2260, 2351)
        assert pb.rango_captura(GROUDON, 25) == (2825, 2939)

    def test_el_potenciado_siempre_es_mayor(self) -> None:
        for stats in (GROUDON, XERNEAS):
            n20 = pb.rango_captura(stats, 20)
            n25 = pb.rango_captura(stats, 25)
            assert n25[0] > n20[0]
            assert n25[1] > n20[1]

    def test_el_maximo_supera_al_minimo(self) -> None:
        minimo, maximo = pb.rango_captura(XERNEAS, 20)
        assert maximo > minimo

    def test_las_capturas_tienen_suelo_de_iv(self) -> None:
        """En incursion no bajan de 10/10/10; por eso el minimo no es con IV 0."""
        assert pb.IV_MIN == 10
        assert pb.calcular_pc(GROUDON, 20, 0) < pb.rango_captura(GROUDON, 20)[0]

    def test_nunca_baja_de_diez(self) -> None:
        assert pb.calcular_pc({"baseAttack": 1, "baseDefense": 1, "baseStamina": 1}, 20, 0) >= 10


class TestTipos:
    def test_normaliza_el_formato_de_pokebattler(self) -> None:
        entrada = {"type": "POKEMON_TYPE_FAIRY", "type2": "POKEMON_TYPE_STEEL"}
        assert pb.tipos_de(entrada) == ["fairy", "steel"]

    def test_un_solo_tipo(self) -> None:
        assert pb.tipos_de({"type": "POKEMON_TYPE_GROUND"}) == ["ground"]

    def test_los_tipos_encajan_con_el_traductor_de_colores(self) -> None:
        """El formato normalizado tiene que servir para elegir los acentos."""
        from hxq_agent.brand.tipos import normalizar_tipo

        for t in pb.tipos_de({"type": "POKEMON_TYPE_FAIRY", "type2": "POKEMON_TYPE_STEEL"}):
            assert normalizar_tipo(t) is not None


class TestFormas:
    @pytest.mark.parametrize(
        ("id_pb", "esperado"),
        [
            ("METAGROSS_MEGA", "Mega Metagross"),
            ("METAGROSS", "Metagross"),
            ("KYUREM_BLACK_FORM", "Kyurem Negro"),
            ("KYUREM_WHITE_FORM", "Kyurem Blanco"),
            ("ZAMAZENTA_CROWNED_SHIELD_FORM", "Zamazenta Escudo Supremo"),
            ("TYPHLOSION_HISUIAN_FORM", "Typhlosion de Hisui"),
            ("CHARIZARD_MEGA_Y", "Mega Charizard Y"),
            ("MEWTWO_SHADOW_FORM", "Mewtwo oscuro"),
            ("GROUDON_PRIMAL", "Groudon primigenio"),
        ],
    )
    def test_decoran_el_nombre(self, id_pb: str, esperado: str) -> None:
        base, forma = tr.separar_forma(id_pb)
        assert tr.aplicar_forma(base.title(), forma) == esperado

    def test_las_formas_evitan_duplicados(self) -> None:
        """Sin esto, KYUREM_BLACK y KYUREM_WHITE salian los dos como 'Kyurem',
        porque comparten numero de Pokedex."""
        nombres = {
            tr.aplicar_forma(*(lambda b, f: (b.title(), f))(*tr.separar_forma(i)))
            for i in ("KYUREM", "KYUREM_BLACK_FORM", "KYUREM_WHITE_FORM")
        }
        assert len(nombres) == 3

    def test_el_sufijo_mas_largo_gana(self) -> None:
        """_ALOLA_SHADOW_FORM no debe detectarse como _SHADOW_FORM."""
        base, forma = tr.separar_forma("RAICHU_ALOLA_SHADOW_FORM")
        assert base == "RAICHU"
        assert tr.aplicar_forma("Raichu", forma) == "Raichu de Alola oscuro"

    @pytest.mark.parametrize(
        ("id_pb", "es"),
        [("METAGROSS_MEGA", True), ("GROUDON_PRIMAL", True), ("METAGROSS", False)],
    )
    def test_detecta_las_megas(self, id_pb: str, es: bool) -> None:
        assert tr.es_mega(id_pb) is es


class TestMovimientos:
    @pytest.mark.parametrize(
        ("pb_name", "slug"),
        [
            ("METAL_CLAW_FAST", "metal-claw"),
            ("BEHEMOTH_BASH", "behemoth-bash"),
            ("FUTURE_SIGHT_PLUS", "future-sight"),
            ("PSYCHO_CUT_FAST", "psycho-cut"),
        ],
    )
    def test_slug_para_pokeapi(self, pb_name: str, slug: str) -> None:
        assert tr.slug_movimiento(pb_name) == slug

    @pytest.mark.parametrize(
        ("pb_name", "esperado"),
        [
            ("HIDDEN_POWER_WATER_FAST", "Poder Oculto (Agua)"),
            ("HIDDEN_POWER_FIRE_FAST", "Poder Oculto (Fuego)"),
            ("HIDDEN_POWER_FAST", "Poder Oculto"),
        ],
    )
    def test_poder_oculto_no_pasa_por_pokeapi(self, pb_name: str, esperado: str) -> None:
        """PokeAPI solo tiene la entrada generica; GO lo desglosa por tipo."""
        assert tr._poder_oculto(pb_name) == esperado

    def test_un_movimiento_normal_no_es_poder_oculto(self) -> None:
        assert tr._poder_oculto("METAL_CLAW_FAST") is None


class TestAtribucion:
    def test_existe_y_nombra_a_pokebattler(self) -> None:
        """Es requisito de sus condiciones de uso al publicar datos derivados."""
        assert "Pokébattler" in pb.ATRIBUCION

    def test_el_user_agent_identifica_al_cliente(self) -> None:
        """Tambien lo piden sus condiciones."""
        assert "HuixquiGo" in pb.UA


class TestCache:
    @pytest.mark.parametrize(
        ("nombre", "ttl"),
        [("pokedex", pb.TTL_POKEDEX), ("raids", pb.TTL_RAIDS), ("counters", pb.TTL_COUNTERS)],
    )
    def test_todo_se_cachea(self, nombre: str, ttl: int) -> None:
        """Pokebattler pide cache agresiva; el pokedex son 7 MB por descarga."""
        assert ttl > 0

    def test_el_pokedex_se_cachea_mas_que_la_rotacion(self) -> None:
        assert pb.TTL_POKEDEX > pb.TTL_RAIDS
