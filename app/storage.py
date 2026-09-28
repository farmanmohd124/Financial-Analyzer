"""Store uploaded PDFs in Azure Blob Storage or on local disk."""

import os
from pathlib import Path


def store_pdf(document_id: str, contents: bytes) -> None:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if connection_string:
        from azure.storage.blob import BlobServiceClient, ContentSettings
        from azure.core.exceptions import ResourceExistsError

        container_name = os.getenv("AZURE_STORAGE_CONTAINER", "filingscope-documents")
        service = BlobServiceClient.from_connection_string(connection_string)
        container = service.get_container_client(container_name)
        try:
            container.create_container()
        except ResourceExistsError:
            pass
        container.upload_blob(
            f"{document_id}.pdf",
            contents,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/pdf"),
        )
        return

    upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{document_id}.pdf").write_bytes(contents)