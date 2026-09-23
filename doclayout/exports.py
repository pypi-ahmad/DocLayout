"""File exports from one extracted document, shared with the GUI exporters."""

import json
from pathlib import Path, PurePosixPath

from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.json import JSONRenderer
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.ui.exports import annotations, image_bytes, markdown_html, output_zip

EXPORT_FILES = {
    "markdown": "document.md",
    "html": "document.html",
    "json": "document.json",
    "chunks": "chunks.json",
    "metadata": "metadata.json",
    "annotated_pdf": "annotated.pdf",
    "zip": "document.zip",
}
ALL_FORMATS = frozenset((*EXPORT_FILES, "images", "annotated_images"))


def output_targets(directory, source, names):
    """Validate every destination before writing any output."""
    root = Path(directory).resolve()
    source = Path(source).resolve()
    if root.exists() and not root.is_dir():
        raise ValueError("The output directory is an existing file")
    targets = {}
    for name in names:
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or ":" in name
        ):
            raise ValueError("Unsafe output filename")
        target = (root / name).resolve()
        if not target.is_relative_to(root) or target == root:
            raise ValueError("Output must stay inside the output directory")
        if target == source or (target.exists() and target.samefile(source)):
            raise ValueError("Output would overwrite the input document")
        if target.is_dir():
            raise ValueError(f"An output filename is an existing directory: {name}")
        if target in targets.values():
            raise ValueError("Output filenames collide")
        targets[name] = target
    return targets


def document_exports(document, config, formats):
    """Return only requested files as bytes; a ZIP contains the full GUI bundle."""
    formats = set(formats)
    needed = ALL_FORMATS if "zip" in formats else formats
    markdown = MarkdownRenderer(config)(document)
    result = {
        "markdown": markdown.markdown,
        "images": markdown.images,
        "metadata": markdown.metadata,
    }
    if "html" in needed:
        result["html"] = markdown_html(markdown.markdown, markdown.images)
    if "json" in needed:
        result["json"] = JSONRenderer(config)(document).model_dump_json(indent=2)
    if "chunks" in needed:
        result["chunks"] = ChunkRenderer(config)(document).model_dump_json(indent=2)
    if {"annotated_pdf", "annotated_images"} & needed:
        result["annotations"] = annotations(document)

    outputs = {}
    for kind in formats & {"markdown", "html", "json", "chunks"}:
        outputs[EXPORT_FILES[kind]] = result[kind].encode("utf-8")
    if "metadata" in formats:
        outputs[EXPORT_FILES["metadata"]] = json.dumps(
            result["metadata"], indent=2
        ).encode("utf-8")
    if "annotated_pdf" in formats:
        outputs[EXPORT_FILES["annotated_pdf"]] = result["annotations"]["pdf"]
    if "annotated_images" in formats:
        for page, image in result["annotations"]["pages"].items():
            outputs[f"annotations/page-{page}.png"] = image_bytes(image)
    if {"markdown", "images"} & formats:
        for name, image in result["images"].items():
            if name.casefold() in {
                value.casefold() for value in EXPORT_FILES.values()
            } or name.startswith("annotations/"):
                raise ValueError("Image filename collides with a document export")
            image_format = (
                "JPEG"
                if PurePosixPath(name).suffix.lower() in (".jpg", ".jpeg")
                else "PNG"
            )
            outputs[name] = image_bytes(image, image_format)
    if "zip" in formats:
        outputs[EXPORT_FILES["zip"]] = output_zip(result)
    return outputs


def save_document_exports(outputs, directory, source):
    targets = output_targets(directory, source, outputs)
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(outputs[name])
