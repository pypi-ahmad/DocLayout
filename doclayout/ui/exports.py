"""In-memory document exports and estimated geometry overlays."""

import base64
import io
import json
import math
import re
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

import bleach
import markdown2
from bs4 import BeautifulSoup
from PIL import ImageDraw

from doclayout.filenames import export_filename
from doclayout.schema.polygon import PolygonBox

STYLE = """
body {background:white;color:black;font-family:Georgia,'Times New Roman',serif;
max-width:800px;margin:0 auto;padding:24px;line-height:1.5;overflow-wrap:anywhere}
h1 {font-size:1.6em;border-bottom:2px solid black;padding-bottom:4px}
h2 {font-size:1.25em;margin-top:1.2em} table {border-collapse:collapse;width:100%;margin:12px 0}
th,td {border:1px solid #333;padding:6px 10px;text-align:left} th {background:#eee}
p {margin:.6em 0} img {max-width:100%;height:auto} pre {overflow:auto;background:#eee;padding:12px}
"""


def image_bytes(image, format="PNG"):
    """Encode an image as RGB bytes.

    Args:
        image (PIL.Image.Image): Image to encode without modifying the original.
        format (str): Pillow output format, normally PNG or JPEG.

    Returns:
        bytes: Encoded image.

    Raises:
        OSError: Pillow cannot encode the requested image.
        KeyError: The requested format has no registered encoder.
    """
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format=format)
    return buffer.getvalue()


def markdown_preview(markdown: str, images: dict) -> str:
    """Return sanitized preview HTML without the export's fixed white-page style."""
    soup = BeautifulSoup(markdown_html(markdown, images), "html.parser")
    return "<div>" + soup.body.decode_contents() + "</div>"


def markdown_html(markdown: str, images: dict) -> str:
    """Render sanitized standalone HTML using only known extracted images.

    Args:
        markdown (str): Converted document text.
        images (dict): Source image names mapped to Pillow images.

    Returns:
        str: Styled HTML with embedded images and supported LaTeX conversion.
        Unknown image sources are removed; remote resources are not fetched.

    Raises:
        OSError: An extracted image cannot be encoded.
    """
    body = markdown2.markdown(
        markdown, extras=["tables", "fenced-code-blocks", "strike", "task_list"]
    )
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup.find_all(["script", "style", "iframe", "object", "svg"]):
        tag.decompose()
    # Only the extracted image map can introduce image data URLs.
    for tag in soup.find_all("img"):
        if tag.get("src") not in images:
            tag.decompose()
    tags = set(bleach.sanitizer.ALLOWED_TAGS) | {
        "p",
        "div",
        "span",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "pre",
        "code",
        "del",
        "img",
        "sup",
        "sub",
    }
    body = bleach.clean(
        str(soup),
        tags=tags,
        attributes={
            "a": ["href", "title"],
            "img": ["src", "alt"],
            "th": ["colspan", "rowspan"],
            "td": ["colspan", "rowspan"],
        },
        protocols=["https", "http", "mailto"],
        strip=True,
    )
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup.find_all("img"):
        source = tag.get("src")
        if source in images:
            tag["src"] = (
                "data:image/png;base64,"
                + base64.b64encode(image_bytes(images[source])).decode()
            )
        else:
            tag.decompose()
    # Math is generated locally after sanitizing document markup. Failed conversion
    # retains the original readable LaTeX, and code blocks are never interpreted.
    from latex2mathml.converter import convert

    for node in list(soup.find_all(string=True)):
        if any(parent.name in ("pre", "code") for parent in node.parents):
            continue
        pattern = r"(?<!\\)(\$\$[\s\S]+?\$\$|\$[^\n$]+?\$)"
        if not re.search(pattern, str(node)):
            continue
        parts = re.split(pattern, str(node))
        for part in parts:
            if part.startswith("$") and part.endswith("$"):
                try:
                    display = "block" if part.startswith("$$") else "inline"
                    markup = convert(part.strip("$"), display=display)
                    markup = bleach.clean(
                        markup,
                        tags={
                            "math",
                            "mrow",
                            "mi",
                            "mn",
                            "mo",
                            "ms",
                            "mtext",
                            "mspace",
                            "mfrac",
                            "msqrt",
                            "mroot",
                            "mstyle",
                            "msub",
                            "msup",
                            "msubsup",
                            "munder",
                            "mover",
                            "munderover",
                            "mtable",
                            "mtr",
                            "mtd",
                            "menclose",
                            "mpadded",
                            "mphantom",
                            "mmultiscripts",
                            "mprescripts",
                            "none",
                            "mfenced",
                        },
                        attributes={
                            "*": [
                                "display",
                                "xmlns",
                                "mathvariant",
                                "stretchy",
                                "columnalign",
                                "rowalign",
                                "columnspacing",
                                "rowspacing",
                                "linethickness",
                                "notation",
                                "width",
                                "height",
                                "depth",
                                "fence",
                                "separator",
                            ]
                        },
                        strip=True,
                    )
                    node.insert_before(BeautifulSoup(markup, "html.parser"))
                    continue
                except Exception:  # noqa: BLE001 - malformed LaTeX stays readable
                    node.insert_before(part)
                    continue
            node.insert_before(part)
        node.extract()
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>DocLayout document</title><style>'
        + STYLE
        + "</style></head><body>"
        + str(soup)
        + "</body></html>"
    )


def annotations(document, config=None):
    """Draw authoritative source footprints and encode a raster annotated PDF.

    Args:
        document (Document): Converted pages with high-resolution images.
        config (dict | None): The same visibility settings used for text rendering.

    Returns:
        dict: One-based page images, PDF bytes, and drawn/skipped box counts.
        Invalid boxes are skipped; source images remain unchanged. Layout-aware
        overlays follow visible final structure and retain source footprints
        for same-page and cross-page merges. Raw masks remain local evidence.

    Raises:
        OSError: Image or PDF encoding fails.
    """
    from doclayout.layout import visible_block, visible_sources
    from doclayout.layout_geometry import transform_points

    pages, skipped, drawn = {}, 0, 0
    geometry_fallbacks = []
    page_counts = {}
    overlays = {}
    if getattr(document, "layout", None) is not None:
        ordinal = 0
        for source_page in document.pages:
            for bid in source_page.structure or []:
                block = document.get_block(bid)
                if not visible_block(block, config):
                    continue
                ordinal += 1
                label = f"{ordinal} {block.id}"
                sources = visible_sources(block, document, config)
                if sources:
                    for source in sources:
                        valid_contours = False
                        if source.contours:
                            from shapely.geometry import Polygon

                            valid_contours = all(
                                len(part) >= 3
                                and all(
                                    len(point) == 2
                                    and all(math.isfinite(v) for v in point)
                                    for point in part
                                )
                                and Polygon(part).is_valid
                                and Polygon(part).area > 0
                                for part in source.contours
                            )
                        if source.contours and not valid_contours:
                            geometry_fallbacks.append(
                                {
                                    "block_id": source.block_id,
                                    "reason": "export_contour_invalid",
                                    "fallback": source.geometry_source.replace(
                                        "contour", "bbox"
                                    ),
                                }
                            )
                        parts = (
                            source.contours
                            if valid_contours
                            else [PolygonBox.from_bbox(source.bbox).polygon]
                        )
                        for part in parts:
                            overlays.setdefault(source.page_id, []).append(
                                (part, label, valid_contours)
                            )
                else:
                    if block.structure and not getattr(block, "html", None):
                        continue
                    overlays.setdefault(source_page.page_id, []).append(
                        (block.polygon.polygon, label, False)
                    )
    for page in document.pages:
        counts = {"contours": 0, "rectangles": 0, "skipped": 0}
        page_counts[page.page_id] = counts
        image = page.get_image(highres=True).convert("RGB").copy()
        draw = ImageDraw.Draw(image)
        if getattr(document, "layout", None) is not None:
            boxes = overlays.get(page.page_id, [])
        else:
            boxes = [
                (b.polygon.polygon, b.block_type.name, False)
                for b in page.children or []
                if not b.removed and not b.structure
            ]
        for polygon, label, is_contour in boxes:
            try:
                points = transform_points(
                    polygon, page.polygon.bbox, [0, 0, image.width, image.height]
                )
                x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
                x1, y1 = max(p[0] for p in points), max(p[1] for p in points)
                if not (
                    all(math.isfinite(v) for point in points for v in point)
                    and 0 <= x0 < x1 <= image.width
                    and 0 <= y0 < y1 <= image.height
                ):
                    raise ValueError("invalid box")
                if is_contour:
                    draw.line(
                        [tuple(p) for p in [*points, points[0]]],
                        fill=(220, 30, 30),
                        width=3,
                    )
                else:
                    draw.rectangle((x0, y0, x1, y1), outline=(220, 30, 30), width=3)
                draw.text((x0, max(0, y0 - 14)), label, fill=(220, 30, 30))
                drawn += 1
                counts["contours" if is_contour else "rectangles"] += 1
            except (ValueError, TypeError, ZeroDivisionError):
                skipped += 1
                counts["skipped"] += 1
        pages[page.page_id + 1] = image
    buffer = io.BytesIO()
    if pages:
        first, *rest = pages.values()
        first.save(buffer, format="PDF", save_all=True, append_images=rest)
    return {
        "pages": pages,
        "pdf": buffer.getvalue(),
        "drawn": drawn,
        "skipped": skipped,
        "geometry_fallbacks": geometry_fallbacks,
        "page_counts": page_counts,
    }


def output_zip(result):
    """Package existing conversion outputs without rerunning conversion.

    Args:
        result (dict): Rendered text, metadata, images, and annotation payloads;
            optional export_base controls shared filenames.

    Returns:
        bytes: ZIP containing conversion exports and annotated page images.

    Raises:
        ValueError: An image filename is unsafe or collides with reserved output.
        KeyError: A required export payload is missing.
        OSError: Image encoding fails.
    """
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, data in {
            "document.md": result["markdown"],
            "document.html": result["html"],
            "document.json": result["json"],
            "chunks.json": result["chunks"],
            "metadata.json": json.dumps(result["metadata"], indent=2),
            "annotated.pdf": result["annotations"]["pdf"],
        }.items():
            archive.writestr(export_filename(result.get("export_base"), name), data)
        reserved = set(archive.namelist())
        for name, image in result["images"].items():
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or name in reserved
                or name.startswith("annotations/")
            ):
                raise ValueError("Unsafe image filename in document output")
            format = "JPEG" if path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
            archive.writestr(name, image_bytes(image, format))
        for page, image in result["annotations"]["pages"].items():
            archive.writestr(
                export_filename(
                    result.get("export_base"), f"annotations/page-{page}.png"
                ),
                image_bytes(image),
            )
    return buffer.getvalue()
