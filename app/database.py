"""SQLite persistence for document metadata and analysis results."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class DocumentDatabase:
    def __init__(self, database_path: str):
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        if str(self.database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def save_document(
        self,
        document_id: str,
        filename: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> dict:
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT created_at FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            created_at = (
                existing["created_at"]
                if existing
                else datetime.now(timezone.utc).isoformat()
            )
            connection.execute(
                """
                INSERT INTO documents (id, filename, status, result_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename,
                    status = excluded.status,
                    result_json = excluded.result_json,
                    error = excluded.error
                """,
                (document_id, filename, status, json.dumps(result) if result is not None else None, error, created_at),
            )
        document = self.get_document(document_id)
        if document is None:
            raise RuntimeError("Saved document could not be loaded")
        return document

    def get_document(self, document_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return self._serialize(row) if row else None

    def list_documents(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY created_at DESC"
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict:
        document = {
            "id": row["id"],
            "filename": row["filename"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "created_at": row["created_at"],
        }
        if row["error"]:
            document["error"] = row["error"]
        return document