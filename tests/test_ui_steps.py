"""La capa que entrega los archivos al admin.

Regresion importante: MAF devuelve el resultado de una tool como `list[Content]`, no
como `str`. Hacerle `str()` da `[<Content object at 0x...>]`, y eso rompia dos cosas a
la vez sin dar ningun error: el panel de la tool mostraba ese repr, y la imagen y el
calendario nunca se le adjuntaban al admin. Los archivos se generaban y no habia forma
de obtenerlos.
"""

from __future__ import annotations

import pytest

from hxq_agent.ui.steps import rutas_generadas, texto_resultado


class _ContentFalso:
    def __init__(self, text: str) -> None:
        self.text = text


class TestTextoResultado:
    def test_una_lista_de_content_da_su_texto(self) -> None:
        """El caso real: MAF entrega list[Content]."""
        assert texto_resultado([_ContentFalso("hola")]) == "hola"

    def test_varios_content_se_unen(self) -> None:
        assert texto_resultado([_ContentFalso("a"), _ContentFalso("b")]) == "a\nb"

    def test_un_content_suelto(self) -> None:
        assert texto_resultado(_ContentFalso("hola")) == "hola"

    def test_un_str_pasa_tal_cual(self) -> None:
        assert texto_resultado("hola") == "hola"

    def test_none_da_cadena_vacia(self) -> None:
        assert texto_resultado(None) == ""

    def test_nunca_devuelve_un_repr_de_objeto(self) -> None:
        """La firma del bug: '<... object at 0x...>' en la salida."""
        salida = texto_resultado([_ContentFalso("/tmp/x.png")])
        assert "object at 0x" not in salida


class TestRutasGeneradas:
    def test_encuentra_el_png_que_devuelve_la_tool(self, tmp_path) -> None:
        png = tmp_path / "quedada_abc.png"
        png.write_bytes(b"x")
        texto = f"Pieza 'quedada' generada: {png}\nTitulo: Prueba"
        assert rutas_generadas(texto) == [png]

    def test_encuentra_el_ics(self, tmp_path) -> None:
        ics = tmp_path / "quedada.ics"
        ics.write_bytes(b"x")
        assert rutas_generadas(f"Archivo de calendario generado: {ics}") == [ics]

    def test_los_dos_juntos(self, tmp_path) -> None:
        png, ics = tmp_path / "a.png", tmp_path / "b.ics"
        png.write_bytes(b"x")
        ics.write_bytes(b"x")
        assert len(rutas_generadas(f"{png}\n{ics}")) == 2

    def test_ignora_rutas_que_no_existen(self) -> None:
        """El modelo a veces repite una ruta en su propio texto."""
        assert rutas_generadas("mira /tmp/no-existe-jamas.png") == []

    def test_no_duplica(self, tmp_path) -> None:
        png = tmp_path / "a.png"
        png.write_bytes(b"x")
        assert len(rutas_generadas(f"{png} y otra vez {png}")) == 1

    @pytest.mark.parametrize("basura", ["", "sin rutas aqui", "archivo.png sin directorio"])
    def test_texto_sin_rutas(self, basura: str) -> None:
        assert rutas_generadas(basura) == []

    def test_el_flujo_completo_desde_list_content(self, tmp_path) -> None:
        """De lo que devuelve MAF a los archivos que ve el admin, sin pasos intermedios."""
        png = tmp_path / "pieza.png"
        png.write_bytes(b"x")
        resultado = [_ContentFalso(f"Pieza 'quedada' generada: {png}")]
        assert rutas_generadas(texto_resultado(resultado)) == [png]
