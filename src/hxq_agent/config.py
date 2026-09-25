"""Configuracion centralizada, leida de entorno o de `.env`.

Un solo lugar donde vive la configuracion. Nada mas en el proyecto lee `os.environ`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion de la aplicacion.

    Los nombres de campo se mapean a variables de entorno en mayusculas:
    `azure_openai_endpoint` <- `AZURE_OPENAI_ENDPOINT`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- Modelo ----------
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    # Vacio a proposito: cada cliente de MAF tiene su propio default correcto segun la
    # superficie de API (Responses usa "preview", Chat Completions "2024-12-01-preview",
    # Embeddings "2024-10-21"). Fijar un valor unico aqui rompe al que no coincida.
    # Solo rellenar para clavar una version concreta a proposito.
    azure_openai_api_version: str = ""
    hxq_chat_deployment: str = "gpt-5.6-luna"
    hxq_image_deployment: str = "gpt-image-1.5"

    # ---------- Tools ----------
    tavily_api_key: str = ""
    # Fuentes en las que confiamos para datos de eventos oficiales. Separadas por coma
    # para poder ajustarlas sin redeploy.
    hxq_official_sources: str = "pokemongolive.com,leekduck.com,serebii.net"

    # ---------- Acceso ----------
    # Lista de correos separada por comas. Vacia = nadie entra (fail closed).
    hxq_admin_emails: str = ""

    # ---------- Contexto de la comunidad ----------
    hxq_community_name: str = "la comunidad"
    hxq_community_city: str = "Mexico"
    hxq_timezone: str = "America/Mexico_City"

    @property
    def admin_emails(self) -> frozenset[str]:
        """Allowlist normalizada a minusculas y sin espacios."""
        return frozenset(
            email.strip().lower() for email in self.hxq_admin_emails.split(",") if email.strip()
        )

    @property
    def official_sources(self) -> list[str]:
        """Dominios confiables para datos de eventos oficiales."""
        return [d.strip() for d in self.hxq_official_sources.split(",") if d.strip()]

    @property
    def uses_managed_identity(self) -> bool:
        """Sin API key configurada asumimos Managed Identity / az login."""
        return not self.azure_openai_api_key.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings cacheados: se leen una sola vez por proceso."""
    return Settings()
