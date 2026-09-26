# Modified for DocLayout; see NOTICE for a summary of changes.
from typing import Any, List, Optional, Sequence, Union

from pdftext.schema import Reference
from PIL import Image, ImageDraw
from pydantic import computed_field

from doclayout.schema import BlockTypes
from doclayout.schema.blocks import Block, BlockId
from doclayout.schema.blocks.base import BlockMetadata
from doclayout.schema.groups.base import Group
from doclayout.schema.polygon import PolygonBox


class PageGroup(Group):
    block_type: BlockTypes = BlockTypes.Page
    # This is bytes if it is serialized
    lowres_image: Image.Image | None | bytes = None
    highres_image: Image.Image | None | bytes = None
    children: List[Union[Any, Block]] | None = None
    block_description: str = "A single page in the document."
    refs: List[Reference] | None = None
    ocr_errors_detected: bool = False

    def incr_block_id(self):
        if self.block_id is None:
            self.block_id = 0
        else:
            self.block_id += 1

    def add_child(self, block: Block):
        if self.children is None:
            self.children = [block]
        else:
            self.children.append(block)

    def get_image(
        self,
        *args,
        highres: bool = False,
        remove_blocks: Sequence[BlockTypes] | None = None,
        **kwargs,
    ):
        image = self.highres_image if highres else self.lowres_image

        # Check if RGB, convert if needed
        if isinstance(image, Image.Image) and image.mode != "RGB":
            image = image.convert("RGB")

        # Avoid double OCR for certain elements
        if remove_blocks:
            image = image.copy()
            draw = ImageDraw.Draw(image)
            bad_blocks = [
                block
                for block in self.current_children
                if block.block_type in remove_blocks
            ]
            for bad_block in bad_blocks:
                poly = bad_block.polygon.rescale(self.polygon.size, image.size).polygon
                poly = [(int(p[0]), int(p[1])) for p in poly]
                draw.polygon(poly, fill="white")

        return image

    @computed_field
    @property
    def current_children(self) -> List[Block]:
        return [child for child in self.children if not child.removed]

    def get_next_block(
        self,
        block: Optional[Block] = None,
        ignored_block_types: Optional[List[BlockTypes]] = None,
    ):
        if ignored_block_types is None:
            ignored_block_types = []

        structure_idx = 0
        if block is not None:
            pos = self.structure_index(block.id)
            if pos is None:
                return None
            structure_idx = pos + 1

        # Iterate over blocks following the given block
        for next_block_id in self.structure[structure_idx:]:
            if next_block_id.block_type not in ignored_block_types:
                return self.get_block(next_block_id)

        return None  # No valid next block found

    def get_prev_block(self, block: Block):
        block_idx = self.structure_index(block.id)
        if block_idx:
            return self.get_block(self.structure[block_idx - 1])
        return None

    def add_block(self, block_cls: type[Block], polygon: PolygonBox) -> Block:
        self.incr_block_id()
        block = block_cls(
            polygon=polygon,
            block_id=self.block_id,
            page_id=self.page_id,
        )
        self.add_child(block)
        return block

    def add_full_block(self, block: Block) -> Block:
        self.incr_block_id()
        block.block_id = self.block_id
        self.add_child(block)
        return block

    def get_block(self, block_id: BlockId) -> Block | None:
        block: Block = self.children[block_id.block_id]
        assert block.block_id == block_id.block_id
        return block

    def assemble_html(
        self, document, child_blocks, parent_structure=None, block_config=None
    ):
        template = ""
        for c in child_blocks:
            template += f"<content-ref src='{c.id}'></content-ref>"
        return template

    def replace_block(self, block: Block, new_block: Block):
        if block.layout is not None and new_block.layout is None:
            new_block.layout = block.layout.model_copy(deep=True)
            new_block.layout.status = "processor"
        # Handles incrementing the id
        self.add_full_block(new_block)

        # Replace block id in structure
        super().replace_block(block, new_block)

        # Replace block in structure of children
        for child in self.children:
            child.replace_block(block, new_block)

        # Mark block as removed
        block.removed = True

    def aggregate_block_metadata(self) -> BlockMetadata:
        metadata = (
            self.metadata.model_copy() if self.metadata is not None else BlockMetadata()
        )
        for block in self.current_children:
            if block.metadata is not None:
                metadata = metadata.merge(block.metadata)
        return metadata
