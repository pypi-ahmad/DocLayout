"""Local artifacts and short SQLite transactions; model calls never hold a lock."""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from doclayout.fields import compact
from doclayout.settings import settings

WRITE_LOCK = RLock()


def storage_root():
    """Return the Path below OUTPUT_DIR used for local field artifacts."""
    return Path(settings.OUTPUT_DIR) / "field_extraction"


def atomic_write(path, data):
    """Replace one artifact through a temporary file in the same directory.

    Args:
        path (str | Path): Destination; missing parent directories are created.
        data (str | bytes): Content, with strings encoded as UTF-8.

    Raises:
        OSError: Writing, replacing, or cleaning the temporary file fails.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class FieldStore:
    """Persist document manifests, definition snapshots, runs, and field records.

    Args:
        root (str | Path | None): Storage directory; None uses storage_root().

    Attributes:
        root (Path): Local artifact directory containing results.sqlite3.

    Construction creates the directory and SQLite tables when absent. Database
    transactions use a process-local writer lock; SQLite coordinates other processes.
    """

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else storage_root()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, manifest_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS definitions (
                    version TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, definition_version TEXT NOT NULL,
                    status TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS extraction_results (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, status TEXT NOT NULL,
                    fields_json TEXT NOT NULL, evidence_json TEXT NOT NULL, model TEXT NOT NULL,
                    reasoning_effort TEXT NOT NULL, definition_version TEXT NOT NULL,
                    created_at TEXT NOT NULL, error_json TEXT NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        """Yield a sqlite3.Connection under the writer lock, committing on success.

        Exceptions roll back the transaction and propagate. The connection is
        always closed; no model request belongs inside this context manager.
        """
        # ponytail: one writer lock per app process; SQLite coordinates other processes.
        with WRITE_LOCK:
            db = sqlite3.connect(self.root / "results.sqlite3", timeout=30)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

    def document_dir(self, document_id):
        """Return a document's artifact Path without creating it.

        Args:
            document_id (str): Exactly 64 lowercase hexadecimal characters.

        Raises:
            ValueError: The identifier is not a valid document digest.
        """
        if not re.fullmatch(r"[a-f0-9]{64}", document_id):
            raise ValueError("Invalid document identifier.")
        return self.root / "documents" / document_id

    def save_document(self, document_id, filename, manifest):
        """Insert or replace a document manifest; return None.

        Args:
            document_id (str): Document digest used as its primary key.
            filename (str): Original upload name, retained as metadata.
            manifest (dict): JSON-compatible conversion-artifact metadata.
        """
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?)",
                (document_id, filename, compact(manifest)),
            )

    def document(self, document_id):
        """Return a document dict with decoded manifest, or None if absent.

        Args:
            document_id (str): Saved document's primary key.
        """
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE id=?", (document_id,)
            ).fetchone()
        if row is None:
            return None
        return {**dict(row), "manifest": json.loads(row["manifest_json"])}

    def save_result(self, document_id, definition, outcome, usage):
        """Commit a field run and attempt its record JSON exports.

        Args:
            document_id (str): Identifier of an already saved source document.
            definition (Definition): Prompt/schema snapshot for this run.
            outcome (dict): Status, classification, issues, and grounded records.
            usage (list[dict]): Reported model usage, retained in run metadata.

        Returns:
            str: New run ID. Record-export errors are saved for later retry.

        Raises:
            ValueError: The source document has not been saved.
            sqlite3.Error: A database operation fails.
        """
        run_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        document = self.document(document_id)
        if document is None:
            raise ValueError("Source document has not been saved.")
        # Keep ordinary spaces and Unicode in requested export names; reject path syntax.
        stem = Path(document["filename"]).stem
        stem = (
            re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")[:140] or "document"
        )
        metadata = {k: v for k, v in outcome.items() if k != "records"}
        metadata.update(usage=usage, records=[], export_error=None)
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO definitions VALUES (?, ?)",
                (definition.version, compact(asdict(definition))),
            )
            for index, record in enumerate(outcome["records"], 1):
                name = f"{stem}_{index:03d}"
                record_id = f"{run_id}:{index:03d}"
                metadata["records"].append({"id": record_id, "name": name})
                db.execute(
                    "INSERT INTO extraction_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record_id,
                        document_id,
                        record["status"],
                        compact(record["fields"]),
                        compact(record["evidence"]),
                        definition.extraction_model,
                        definition.extraction_reasoning_effort,
                        definition.version,
                        now,
                        compact(record["issues"]),
                    ),
                )
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    document_id,
                    definition.version,
                    outcome["status"],
                    compact(metadata),
                    now,
                ),
            )
        self.export_run(run_id)
        return run_id

    def runs(self):
        """Return list[dict] run summaries with filenames, newest first."""
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT runs.*, documents.filename FROM runs JOIN documents ON documents.id=runs.document_id ORDER BY created_at DESC"
                )
            ]

    def run(self, run_id):
        """Return a saved run dict with decoded results and complete records.

        Args:
            run_id (str): Saved run identifier.

        Raises:
            ValueError: No run has that identifier.
        """
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("Saved run not found.")
            result = dict(row)
            result["result"] = json.loads(row["result_json"])
            records = []
            for item in result["result"]["records"]:
                record = dict(
                    db.execute(
                        "SELECT * FROM extraction_results WHERE id=?", (item["id"],)
                    ).fetchone()
                )
                records.append(
                    {
                        "id": record["id"],
                        "name": item["name"],
                        "status": record["status"],
                        "fields": json.loads(record["fields_json"]),
                        "evidence": json.loads(record["evidence_json"]),
                        "issues": json.loads(record["error_json"]),
                        "model": record["model"],
                        "reasoning_effort": record["reasoning_effort"],
                        "definition_version": record["definition_version"],
                    }
                )
            result["records"] = records
            return result

    def export_run(self, run_id):
        """Recreate record JSON from SQLite without model calls.

        Args:
            run_id (str): Existing run to export into its own artifact directory.

        Returns:
            str | None: Safe retry message on file-write failure, otherwise None.
            The same value is persisted in the run's export_error metadata.

        Raises:
            ValueError: The run does not exist.
            sqlite3.Error: Loading or updating the run fails.
        """
        run = self.run(run_id)
        error = None
        try:
            directory = self.document_dir(run["document_id"]) / "runs" / run_id
            for record in run["records"]:
                atomic_write(
                    directory / (record["name"] + ".json"),
                    json.dumps(record, ensure_ascii=False, indent=2),
                )
        except OSError:
            error = "JSON export failed; retry export without rerunning extraction."
        run["result"]["export_error"] = error
        with self.connection() as db:
            db.execute(
                "UPDATE runs SET result_json=? WHERE id=?",
                (compact(run["result"]), run_id),
            )
        return error
