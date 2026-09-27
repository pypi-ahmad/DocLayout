# Modified for DocLayout; see NOTICE for a summary of changes.
import base64
import io
import re
from collections import Counter
from typing import Annotated, Literal, Optional, Tuple

from bs4 import BeautifulSoup
from pydantic import BaseModel

from doclayout.schema import BlockTypes
from doclayout.schema.blocks.base import BlockId, BlockOutput
from doclayout.schema.document import Document
from doclayout.settings import settings
from doclayout.util import assign_config

# Placeholder emitted by Block.assemble_html for each child block.
CONTENT_REF_RE = re.compile(r"<content-ref src='([^']*)'></content-ref>")


class BaseRenderer:
    """Share image extraction, HTML assembly, and metadata across renderers.

    Header/footer flags also control final layout visibility.
    """
    image_blocks: Annotated[
        Tuple[BlockTypes, ...], "The block types to consider as images."
    ] = (BlockTypes.Picture, BlockTypes.Figure, BlockTypes.Diagram)
    extract_images: Annotated[bool, "Extract images from the document."] = True
    image_extraction_mode: Annotated[
        Literal["lowres", "highres"],
        "The mode to use for extracting images.",
    ] = "highres"
    keep_pageheader_in_output: Annotated[
        bool, "Keep the page header in the output HTML."
    ] = False
    keep_pagefooter_in_output: Annotated[
        bool, "Keep the page footer in the output HTML."
    ] = False
    add_block_ids: Annotated[bool, "Whether to add block IDs to the output HTML."] = (
        False
    )

    def __init__(self, config: Optional[BaseModel | dict] = None):
        """Apply renderer settings and pass visibility flags to block rendering.

        Args:
            config (BaseModel | dict | None): Renderer settings accepted by
                ``assign_config``.
        """
        assign_config(self, config)

        self.block_config = {
            "keep_pageheader_in_output": self.keep_pageheader_in_output,
            "keep_pagefooter_in_output": self.keep_pagefooter_in_output,
            "add_block_ids": self.add_block_ids,
        }

    def __call__(self, document):
        """Render a document in the concrete subclass's output format.

        Raises:
            NotImplementedError: The subclass did not provide a renderer.
        """
        # Children are in reading order
        raise NotImplementedError

    def extract_image(self, document: Document, image_id, to_base64=False):
        """Crop a block image at the configured resolution.

        Args:
            document (Document): Document containing the image block.
            image_id (BlockId): ID of the block to crop.
            to_base64 (bool): Encode the crop with the configured image format.

        Returns:
            PIL.Image.Image | str: The crop or its base64-encoded bytes.
        """
        image_block = document.get_block(image_id)
        cropped = image_block.get_image(
            document, highres=self.image_extraction_mode == "highres"
        )

        if to_base64:
            image_buffer = io.BytesIO()
            # RGBA to RGB
            if not cropped.mode == "RGB":
                cropped = cropped.convert("RGB")

            cropped.save(image_buffer, format=settings.OUTPUT_IMAGE_FORMAT)
            cropped = base64.b64encode(image_buffer.getvalue()).decode(
                settings.OUTPUT_ENCODING
            )
        return cropped

    @staticmethod
    def merge_consecutive_math(html, tag="math"):
        """Join adjacent math tags split by a trailing hyphen.

        Args:
            html (str): HTML fragment to normalize.
            tag (str): Math tag name to merge.

        Returns:
            str: HTML with matching adjacent tags joined.
        """
        if not html:
            return html
        pattern = rf"-</{tag}>(\s*)<{tag}>"
        html = re.sub(pattern, " ", html)

        pattern = rf'-</{tag}>(\s*)<{tag} display="inline">'
        html = re.sub(pattern, " ", html)
        return html

    @staticmethod
    def merge_consecutive_tags(html, tag):
        """Join adjacent matching tags while retaining one whitespace gap.

        Args:
            html (str): HTML fragment to normalize.
            tag (str): Tag name to merge.

        Returns:
            str: HTML with consecutive matching tags joined.
        """
        if not html:
            return html

        def replace_whitespace(match):
            whitespace = match.group(1)
            if len(whitespace) == 0:
                return ""
            else:
                return " "

        pattern = rf"</{tag}>(\s*)<{tag}>"

        while True:
            new_merged = re.sub(pattern, replace_whitespace, html)
            if new_merged == html:
                break
            html = new_merged

        return html

    def generate_page_stats(self, document: Document, document_output):
        """Summarize block counts and metadata for each source page.

        Args:
            document (Document): Rendered source document.
            document_output (BlockOutput): Render tree; retained for the shared
                metadata interface and not read by this method.

        Returns:
            list[dict]: Page IDs, extraction methods, block counts, and metadata.
        """
        page_stats = []
        for page in document.pages:
            block_counts = Counter(
                [str(block.block_type) for block in page.children]
            ).most_common()
            block_metadata = page.aggregate_block_metadata()
            page_stats.append(
                {
                    "page_id": page.page_id,
                    "text_extraction_method": page.text_extraction_method,
                    "block_counts": block_counts,
                    "block_metadata": block_metadata.model_dump(),
                }
            )
        return page_stats

    def generate_document_metadata(self, document: Document, document_output):
        """Build usage, page, and optional V3 layout metadata for an export.

        Args:
            document (Document): Source document with usage and page data.
            document_output (BlockOutput | None): Render tree passed through to
                page statistics; callers may supply None.

        Returns:
            dict: Export metadata, including layout provenance when available.
        """
        from doclayout.usage import cost_summary

        metadata = {
            "usage": document.usage,
            "cost": cost_summary(document.usage),
            "extraction": {
                "method": "openai",
                "model": "gpt-6-sol",
                "geometry": "model-estimated",
            },
            "table_of_contents": document.table_of_contents,
            "page_stats": self.generate_page_stats(document, document_output),
        }
        if document.debug_data_path is not None:
            metadata["debug_data_path"] = document.debug_data_path

        from doclayout.layout import layout_metadata

        layout = layout_metadata(document, self.block_config)
        if layout is not None:
            metadata["layout"] = layout
            metadata["extraction"]["geometry"] = "mixed-v3-sol-processor"

        return metadata

    def _splice_block_html(self, document: Document, block_output: BlockOutput):
        # Resolve <content-ref> placeholders by string substitution instead of
        # re-parsing BeautifulSoup at every node of the deep line/span tree
        # (the dominant render cost). Non-image children are inlined; image
        # children keep their content-ref placeholder and contribute their
        # extracted crop to `images` (their sub-tree images are discarded, as
        # before). Returns the raw spliced html; extract_block_html normalizes.
        images = {}
        children = {str(c.id): c for c in (block_output.children or [])}

        def repl(match) -> str:
            child = children.get(match.group(1))
            if child is None:
                return match.group(0)
            block_id: BlockId = child.id
            if block_id.block_type in self.image_blocks and self.extract_images:
                images[block_id] = self.extract_image(
                    document, block_id, to_base64=True
                )
                return match.group(0)
            content, sub_images = self._splice_block_html(document, child)
            images.update(sub_images)
            return content

        html = CONTENT_REF_RE.sub(repl, block_output.html)

        if block_output.id.block_type in self.image_blocks and self.extract_images:
            images[block_output.id] = self.extract_image(
                document, block_output.id, to_base64=True
            )

        return html, images

    def extract_block_html(self, document: Document, block_output: BlockOutput):
        """Resolve child HTML once and collect embedded image crops.

        Args:
            document (Document): Source of image blocks.
            block_output (BlockOutput): Top-level block render tree.

        Returns:
            tuple[str, dict]: Normalized HTML and images keyed by block ID.
        """
        html, images = self._splice_block_html(document, block_output)
        # Normalize once per top-level block (attribute quoting, tag closing) to
        # match the historical output. The splice above already inlined the
        # whole sub-tree as a string, so this is a single parse per block rather
        # than the previous per-node BeautifulSoup re-parse.
        return str(BeautifulSoup(html, "html.parser")), images
