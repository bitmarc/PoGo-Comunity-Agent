"""La puerta de entrada: quien pasa y quien no."""

from __future__ import annotations

import pytest

from hxq_agent.access import email_is_verified, extract_email, is_allowed

ALLOW = frozenset({"admin@hxq.test"})


class TestIsAllowed:
    def test_allowlist_vacia_niega_a_todos(self) -> None:
        """Un despliegue mal configurado no debe ser barra libre."""
        assert is_allowed("admin@hxq.test", frozenset()) is False

    def test_correo_fuera_de_lista(self) -> None:
        assert is_allowed("intruso@otro.com", ALLOW) is False

    @pytest.mark.parametrize("email", ["admin@hxq.test", "ADMIN@HXQ.TEST", "  Admin@Hxq.Test  "])
    def test_normaliza_caso_y_espacios(self, email: str) -> None:
        assert is_allowed(email, ALLOW) is True

    def test_sin_correo(self) -> None:
        assert is_allowed(None, ALLOW) is False
        assert is_allowed("", ALLOW) is False


class TestExtractEmail:
    def test_campo_email_de_google(self) -> None:
        assert extract_email({"email": "  A@X.com "}) == "a@x.com"

    def test_variantes_oidc(self) -> None:
        assert extract_email({"preferred_username": "b@y.com"}) == "b@y.com"
        assert extract_email({"upn": "c@z.com"}) == "c@z.com"

    def test_sin_correo_devuelve_none(self) -> None:
        assert extract_email({}) is None
        assert extract_email({"email": "   "}) is None


class TestEmailIsVerified:
    @pytest.mark.parametrize("value", [False, "false", "False", 0, ""])
    def test_no_verificado(self, value: object) -> None:
        assert email_is_verified({"verified_email": value}) is False

    @pytest.mark.parametrize("value", [True, "true", "TRUE", "1", "yes"])
    def test_verificado(self, value: object) -> None:
        assert email_is_verified({"verified_email": value}) is True

    def test_campo_ausente_no_bloquea(self) -> None:
        """No podemos afirmar que no este verificado si el proveedor no lo dice."""
        assert email_is_verified({}) is True

    def test_variante_oidc(self) -> None:
        assert email_is_verified({"email_verified": False}) is False
