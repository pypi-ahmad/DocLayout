"""Bounded file jobs around the unchanged converter; persistent Markdown retries."""

import hashlib
import io
import json
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Lock
from types import SimpleNamespace
from zipfile import ZipFile

from PIL import Image

from doclayout.field_store import FieldStore, atomic_write
from doclayout.fields import compact, extract_fields
from doclayout.filenames import export_basename, name_result
from doclayout.layout import (
    LayoutUnavailableError,
    SolFallbackEngine,
    get_layout_engine,
    pipeline_manifest,
    prepare_for_conversion,
)
from doclayout.services.openai import ExtractionError
from doclayout.ui.documents import Upload, prepare_upload, run_document
from doclayout.ui.exports import annotations, markdown_html, output_zip

# ponytail: fixed lock stripes bound memory; rare collisions only delay jobs.
DOCUMENT_LOCKS = [Lock() for _ in range(64)]


def conversion_id(filename, data, options):
    """Hash source bytes, filename, options and the current pipeline fingerprint.

    This is a policy identity, not proof that V3 executed successfully. Saved
    page metadata records fallback, and a saved fallback result remains reusable.
    Computing the identity never loads weights or contacts the model Hub.
    """
    return hashlib.sha256(
        data
        + filename.encode()
        + compact(options).encode()
        + pipeline_manifest(options)["fingerprint"].encode()
    ).hexdigest()


def layout_readiness(engine):
    """Return the actual exercised device or the engine's safe readiness text."""
    if engine.status.startswith("Failed:"):
        return "Sol fallback · V3 unavailable"
    device = engine.actual_device
    return f"PP-DocLayoutV3 · {device.upper()}" if device else engine.status


def layout_summary(metadata):
    """Summarize saved page evidence without inference or provider inspection."""
    pages = metadata.get("layout", {}).get("page_runtime", {}).values()
    if not pages:
        return None
    regions = sum(p["retained_region_count"] for p in pages)
    matches = sum(p["matched_count"] for p in pages)
    elapsed = sum(p["elapsed_ms"] for p in pages)
    fallback = sum(p.get("status") == "sol_fallback" for p in pages)
    return (
        f"V3: {regions} regions · {matches} initial matches · "
        f"{elapsed:,.0f} ms summed page analysis (includes queue wait)"
        + (f" · Sol fallback: {fallback} page(s)" if fallback else "")
    )


def finish_exports(result, filename):
    """Add named HTML, annotations, and ZIP to a conversion result in place.

    Args:
        result (dict): Completed converter output with document and images.
        filename (str): Original upload name used for the export basename.

    Returns:
        None: Local rendering mutates result without another model call.
    """
    name_result(result, export_basename(filename))
    result["html"] = markdown_html(result["markdown"], result["images"])
    result["annotations"] = annotations(result["document"])
    result["zip"] = output_zip(result)


def save_conversion(store, document_id, filename, data, upload, result, raw_markdown):
    """Write reusable conversion artifacts, then save their document manifest.

    Args:
        store (FieldStore): Local artifact/database owner.
        document_id (str): Valid document digest.
        filename (str): Original upload name.
        data (bytes): Original uploaded content, retained as source.bin.
        upload (Upload): Prepared preview bytes, suffix, and page count.
        result (dict): Completed conversion and locally assembled exports.
        raw_markdown (str): Source snapshot before export image renaming.

    Raises:
        OSError: An artifact cannot be written; earlier writes may remain.
    """
    directory = store.document_dir(document_id)
    atomic_write(directory / "source.bin", data)
    atomic_write(directory / ("preview" + upload.suffix), upload.data)
    atomic_write(directory / "raw.md", raw_markdown)
    atomic_write(directory / "chunks.json", result["chunks"])
    atomic_write(directory / "conversion.zip", result["zip"])
    manifest = {
        "pipeline": result["metadata"].get("layout", {}).get("manifest", {}),
        "suffix": upload.suffix,
        "count": upload.count,
        "export_base": result["export_base"],
        "pages": result["pages"],
        "image_names": list(result["images"]),
        "annotations": {
            k: v for k, v in result["annotations"].items() if k not in {"pdf", "pages"}
        },
        "selected_pages": list(result["annotations"]["pages"]),
    }
    store.save_document(document_id, filename, manifest)


def load_conversion(store, document_id):
    """Reconstruct conversion views from saved artifacts without model calls.

    Args:
        store (FieldStore): Artifact/database owner.
        document_id (str): Existing document digest.

    Returns:
        tuple[Upload, dict]: Prepared upload and restored display/export results.

    Raises:
        OSError: A required artifact cannot be read.
        KeyError: The saved manifest or archive lacks a required entry.
    """
    document = store.document(document_id)
    info = document["manifest"]
    directory = store.document_dir(document_id)
    upload = Upload(
        (directory / ("preview" + info["suffix"])).read_bytes(),
        info["suffix"],
        info["count"],
    )
    archive_bytes = (directory / "conversion.zip").read_bytes()
    from doclayout.filenames import export_filename

    with ZipFile(io.BytesIO(archive_bytes)) as archive:

        def read(name):
            return archive.read(export_filename(info["export_base"], name))

        def image(name):
            with Image.open(io.BytesIO(archive.read(name))) as opened:
                return opened.copy()

        result = {
            key: read(name).decode("utf-8")
            for key, name in (
                ("markdown", "document.md"),
                ("html", "document.html"),
                ("json", "document.json"),
                ("chunks", "chunks.json"),
            )
        }
        result.update(
            pipeline=info.get("pipeline", {}).get("pipeline", "legacy-sol-only"),
            export_base=info["export_base"],
            zip=archive_bytes,
            metadata=json.loads(read("metadata.json")),
            pages={int(k): v for k, v in info["pages"].items()},
            document=SimpleNamespace(pages=info["selected_pages"]),
            images={name: image(name) for name in info["image_names"]},
            annotations={
                **info["annotations"],
                "pdf": read("annotated.pdf"),
                "pages": {
                    page: image(
                        export_filename(
                            info["export_base"], f"annotations/page-{page}.png"
                        )
                    )
                    for page in info["selected_pages"]
                },
            },
        )
    return upload, result


def retry_fields(store, document_id, definition, *, client=None):
    """Make a new field run from saved Markdown, without reconverting the source.

    Args:
        store (FieldStore): Existing artifact/database owner.
        document_id (str): Source with saved raw.md and chunks.json.
        definition (Definition): Current extraction/classification snapshot.
        client (OpenAI | None): Optional borrowed model client.

    Returns:
        tuple[str, list[dict]]: Newly persisted run ID and request usage.

    Raises:
        OSError: A required source artifact cannot be read.
    """
    directory = store.document_dir(document_id)
    usage = []
    outcome = extract_fields(
        (directory / "raw.md").read_text("utf-8"),
        json.loads((directory / "chunks.json").read_text("utf-8")),
        definition,
        client=client,
        usage=usage,
    )
    return store.save_result(document_id, definition, outcome, usage), usage


def process_file(
    filename,
    data,
    options,
    models,
    definition,
    *,
    root=None,
    prepared=None,
    client=None,
):
    """Process one upload, reusing matching saved conversion and field runs.

    Args:
        filename (str): Original upload name; part of document identity.
        data (bytes): Uploaded content; part of document identity.
        options (dict): Conversion settings; part of document identity.
        models (dict): Existing conversion service artifacts.
        definition (Definition): Field instructions and cache fingerprint.
        root (str | Path | None): Optional local field-store root.
        prepared (Upload | None): Already prepared single-file upload.
        client (OpenAI | None): Optional borrowed downstream model client.

    Returns:
        dict: Completion/failure receipt with usage and, when saved, run ID.
        Matching definitions reuse existing runs even when they need review.
        Processing exceptions become per-file failures so other jobs continue.
    """
    usage = []
    document_id = conversion_id(filename, data, options)
    with DOCUMENT_LOCKS[int(document_id[:2], 16) % len(DOCUMENT_LOCKS)]:
        receipt = {
            "filename": filename,
            "document_id": document_id,
            "status": "failed",
            "usage": usage,
        }
        result = None
        store = None
        try:
            store = FieldStore(root)
            if store.document(document_id) is None:
                atomic_write(store.document_dir(document_id) / "source.bin", data)
                upload = prepared or prepare_upload(data, filename)
                result = run_document(upload, options, models, usage_entries=usage)
                raw_markdown = result[
                    "markdown"
                ]  # Snapshot before existing export image renaming.
                finish_exports(result, filename)
                save_conversion(
                    store, document_id, filename, data, upload, result, raw_markdown
                )
            else:
                existing = next(
                    (
                        r
                        for r in store.runs()
                        if r["document_id"] == document_id
                        and r["definition_version"] == definition.version
                    ),
                    None,
                )
                if existing is not None:
                    return {
                        **receipt,
                        "status": existing["status"],
                        "run_id": existing["id"],
                        "reused": True,
                    }
            run_id, field_usage = retry_fields(
                store, document_id, definition, client=client
            )
            usage.extend(field_usage)
            receipt.update(run_id=run_id, status=store.run(run_id)["status"])
        except Exception as exc:  # noqa: BLE001 - isolate document failures without exposing source data
            detail = (
                str(exc)
                if isinstance(exc, (ExtractionError, LayoutUnavailableError))
                else type(exc).__name__
            )
            receipt["error"] = (
                f"Document processing failed ({detail}). Other files continue."
            )
            if store is not None:
                try:
                    atomic_write(
                        store.document_dir(document_id) / "failure.json",
                        compact(receipt),
                    )
                except OSError:
                    receipt["error"] += " Failure receipt could not be saved."
        finally:
            if result is not None:
                images = list(result.get("images", {}).values()) + list(
                    result.get("annotations", {}).get("pages", {}).values()
                )
                for page in result["document"].pages:
                    images.extend([page.highres_image, page.lowres_image])
                for image in images:
                    if image is not None:
                        image.close()
        return receipt


def process_batch(
    files, options, models, definition, *, root=None, prepared=None, on_status=None
):
    """Queue all uploads with three active file jobs, without worker UI calls.

    Args:
        files (Iterable[tuple[str, bytes]]): Upload names and original bytes.
        options (dict): Shared conversion options; the GUI sets all pages for batches.
        models (dict): Shared conversion artifacts with existing page-call limits.
        definition (Definition): One field-definition snapshot for the batch.
        root (str | Path | None): Optional store root passed to every file job.
        prepared (Upload | None): Existing single-file preview, never for a batch.
        on_status (Callable | None): Readiness callback invoked only on the caller thread.

    Yields:
        dict: Per-file receipts in completion order, not upload order.
    """
    files = list(files)
    if prepared is not None and len(files) != 1:
        raise ValueError("Prepared upload requires exactly one file")
    if not files:
        return
    store = FieldStore(root)
    identities = [
        (name, data, conversion_id(name, data, options)) for name, data in files
    ]
    uncached = {
        document_id
        for _, _, document_id in identities
        if store.document(document_id) is None
    }
    engine = None
    with ThreadPoolExecutor(max_workers=3) as pool:
        if uncached:
            engine = models.get("layout_engine") or get_layout_engine()
            if on_status is not None and engine.actual_device is None:
                on_status("Preparing layout model…")

            def prepare_layout():
                engine.retry_failed()
                return prepare_for_conversion(engine)

            preparation = pool.submit(prepare_layout)
            while not preparation.done():
                wait([preparation], timeout=0.25)
            try:
                engine = preparation.result()
            except Exception:  # noqa: BLE001 - includes failure to reset a failed backend
                engine = SolFallbackEngine()
            models = {**models, "layout_engine": engine}
            if on_status is not None:
                on_status(layout_readiness(engine))
        jobs = [
            pool.submit(
                process_file,
                name,
                data,
                options,
                models,
                definition,
                root=root,
                prepared=prepared,
            )
            for name, data in files
        ]
        pending = set(jobs)
        while pending:
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            if on_status is not None and engine is not None:
                on_status(layout_readiness(engine))
            for future in done:
                yield future.result()
