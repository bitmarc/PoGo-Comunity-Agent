"""Cliente de Azure Blob Storage para los archivos de Chainlit.

Chainlit trae un `AzureBlobStorageClient`, pero exige una storage key. Este usa
`DefaultAzureCredential`, asi que en Azure Container Apps funciona con Managed Identity y
no hay ninguna clave de larga vida en el entorno. En local usa `az login`.

Las URLs de lectura se firman con una user delegation key, que es el equivalente de un SAS
cuando no tienes la clave de la cuenta: se pide a Azure con la identidad y caduca.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from chainlit.data.storage_clients.base import BaseStorageClient

logger = logging.getLogger(__name__)

# Cuanto vale una URL de lectura. Corto a proposito: la UI la pide cuando la necesita.
DURACION_URL = timedelta(hours=1)
# Margen hacia atras por desfase de reloj entre el contenedor y Azure.
_MARGEN_RELOJ = timedelta(minutes=5)


class ManagedIdentityBlobStorageClient(BaseStorageClient):
    """Almacena los elementos de Chainlit en Blob Storage usando Entra, sin claves."""

    def __init__(self, account: str, container: str) -> None:
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.blob.aio import BlobServiceClient

        self.account = account
        self.container = container
        self._account_url = f"https://{account}.blob.core.windows.net"
        self._credential = DefaultAzureCredential()
        self._service = BlobServiceClient(self._account_url, credential=self._credential)
        # La user delegation key se reutiliza mientras siga vigente: pedirla en cada
        # get_read_url seria una llamada de red por imagen mostrada.
        self._delegation_key: Any | None = None
        self._delegation_expira: datetime | None = None

    async def upload_file(
        self,
        object_key: str,
        data: bytes | str,
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: str | None = None,
    ) -> dict[str, Any]:
        from azure.storage.blob import ContentSettings

        try:
            blob = self._service.get_blob_client(self.container, object_key)
            await blob.upload_blob(
                data,
                overwrite=overwrite,
                content_settings=ContentSettings(
                    content_type=mime, content_disposition=content_disposition
                ),
            )
        except Exception:
            logger.exception("Fallo al subir %s a Blob Storage", object_key)
            return {}

        return {
            "object_key": object_key,
            "url": f"{self._account_url}/{self.container}/{object_key}",
        }

    async def _obtener_delegation_key(self) -> Any:
        ahora = datetime.now(UTC)
        vigente = (
            self._delegation_key is not None
            and self._delegation_expira is not None
            and ahora < self._delegation_expira - _MARGEN_RELOJ
        )
        if vigente:
            return self._delegation_key

        expira = ahora + timedelta(days=1)
        self._delegation_key = await self._service.get_user_delegation_key(
            key_start_time=ahora - _MARGEN_RELOJ, key_expiry_time=expira
        )
        self._delegation_expira = expira
        return self._delegation_key

    async def get_read_url(self, object_key: str) -> str:
        """URL temporal de lectura, firmada con user delegation key."""
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        ahora = datetime.now(UTC)
        sas = generate_blob_sas(
            account_name=self.account,
            container_name=self.container,
            blob_name=object_key,
            user_delegation_key=await self._obtener_delegation_key(),
            permission=BlobSasPermissions(read=True),
            start=ahora - _MARGEN_RELOJ,
            expiry=ahora + DURACION_URL,
        )
        return f"{self._account_url}/{self.container}/{object_key}?{sas}"

    async def delete_file(self, object_key: str) -> bool:
        try:
            await self._service.get_blob_client(self.container, object_key).delete_blob()
            return True
        except Exception:
            logger.exception("Fallo al borrar %s de Blob Storage", object_key)
            return False

    async def close(self) -> None:
        await self._service.close()
        await self._credential.close()
