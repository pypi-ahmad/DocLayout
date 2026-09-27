# Modified for DocLayout; see NOTICE for a summary of changes.
import html
from typing import Dict, List

from bs4 import BeautifulSoup
from pydantic import BaseModel

from doclayout.renderers.json import JSONBlockOutput, JSONRenderer
from doclayout.schema.document import Document


class FlatBlockOutput(BaseModel):
    id: str
    block_type: str
    html: str
    page: int
    polygon: List[List[float]]
    bbox: List[float]
    section_hierarchy: Dict[int, str] | None = None
    images: dict | None = None


class ChunkOutput(BaseModel):
    blocks: List[FlatBlockOutput]
    page_info: Dict[int, dict]
    metadata: dict


def collect_images(block: JSONBlockOutput) -> dict[str, str]:
    """Collect images attached to a JSON block and its descendants."""
    if not getattr(block, "children", None):
        return block.images or {}
    else:
        images = block.images or {}
        for child_block in block.children:
            images.update(collect_images(child_block))
        return images


def assemble_html_with_images(block: JSONBlockOutput, image_blocks: set[str]) -> str:
    """Resolve child references and image placeholders in a JSON block."""
    # Operates only on the top-level/group block tree: leaf-type blocks are
    # already flattened into a single html string by extract_block_html (they
    # carry no children here), so this hits the no-parse branch for them and
    # only re-parses the shallow group blocks. Kept on BeautifulSoup because its
    # historical escape-then-unescape of inlined children is load-bearing for
    # byte-identical output (e.g. literal <img> tags in figure groups).
    if not getattr(block, "children", None):
        if block.block_type in image_blocks:
            return f"<p>{block.html}<img src='{block.id}'></p>"
        else:
            return block.html

    child_html = [
        assemble_html_with_images(child, image_blocks) for child in block.children
    ]
    child_ids = [child.id for child in block.children]

    soup = BeautifulSoup(block.html, "html.parser")
    content_refs = soup.find_all("content-ref")
    for ref in content_refs:
        src_id = ref.attrs["src"]
        if src_id in child_ids:
            ref.replace_with(child_html[child_ids.index(src_id)])

    return html.unescape(str(soup))


def json_to_chunks(
    block: JSONBlockOutput, image_blocks: set[str], page_id: int = 0
) -> FlatBlockOutput | List[FlatBlockOutput]:
    """Flatten a page or block to chunk records without changing its HTML.

    Args:
        block: JSON-rendered page or block.
        image_blocks: Block-type names rendered with image placeholders.
        page_id: Parent page ID when ``block`` is not itself a page.

    Returns:
        A list for a page, or one FlatBlockOutput for another block.
    """
    if block.block_type == "Page":
        children = block.children
        page_id = int(block.id.split("/")[2])
        return [
            json_to_chunks(child, image_blocks, page_id=page_id) for child in children
        ]
    else:
        return FlatBlockOutput(
            id=block.id,
            block_type=block.block_type,
            html=assemble_html_with_images(block, image_blocks),
            page=page_id,
            polygon=block.polygon,
            bbox=block.bbox,
            section_hierarchy=block.section_hierarchy,
            images=collect_images(block),
        )


class ChunkRenderer(JSONRenderer):
    """Render top-level page children as flat blocks with page bounds."""

    def __call__(self, document: Document) -> ChunkOutput:
        """Return flattened chunks, page geometry, and shared metadata."""
        document_output = document.render(self.block_config)
        json_output = []
        for page_output in document_output.children:
            json_output.append(self.extract_json(document, page_output))

        # This will get the top-level blocks from every page
        chunk_output = []
        for item in json_output:
            chunks = json_to_chunks(
                item, set([str(block) for block in self.image_blocks])
            )
            chunk_output.extend(chunks)

        page_info = {
            page.page_id: {"bbox": page.polygon.bbox, "polygon": page.polygon.polygon}
            for page in document.pages
        }

        return ChunkOutput(
            blocks=chunk_output,
            page_info=page_info,
            metadata=self.generate_document_metadata(document, document_output),
        )
