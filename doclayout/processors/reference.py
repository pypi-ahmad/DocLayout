# Modified for DocLayout; see NOTICE for a summary of changes.
import numpy as np

from doclayout.processors import BaseProcessor
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import Reference
from doclayout.schema.document import Document
from doclayout.schema.groups.figure import FigureGroup
from doclayout.schema.groups.list import ListGroup
from doclayout.schema.groups.table import TableGroup
from doclayout.schema.registry import get_block_class


class ReferenceProcessor(BaseProcessor):
    """
    A processor for adding references to the document.
    """

    def __init__(self, config):
        super().__init__(config)

    def __call__(self, document: Document):
        ReferenceClass: Reference = get_block_class(BlockTypes.Reference)

        for page in document.pages:
            refs = page.refs
            ref_starts = np.array([ref.coord for ref in refs])

            blocks = []
            for block_id in page.structure:
                block = page.get_block(block_id)
                if isinstance(block, (ListGroup, FigureGroup, TableGroup)):
                    # structure_blocks handles structure=None (a layout-detected
                    # group that never received children), returning [].
                    blocks.extend(block.structure_blocks(page))
                else:
                    blocks.append(block)
            blocks = [b for b in blocks if not b.ignore_for_output]

            block_starts = np.array([block.polygon.bbox[:2] for block in blocks])

            if not (len(refs) and len(block_starts)):
                continue

            distances = np.linalg.norm(
                block_starts[:, np.newaxis, :] - ref_starts[np.newaxis, :, :], axis=2
            )
            for ref_idx in range(len(ref_starts)):
                block_idx = np.argmin(distances[:, ref_idx])
                block = blocks[block_idx]

                ref_block = page.add_full_block(
                    ReferenceClass(
                        ref=refs[ref_idx].ref,
                        polygon=block.polygon,
                        page_id=page.page_id,
                    )
                )
                if block.structure is None:
                    block.structure = []
                block.structure.insert(0, ref_block.id)
