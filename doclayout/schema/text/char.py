# Modified for DocLayout; see NOTICE for a summary of changes.
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import Block


class Char(Block):
    block_type: BlockTypes = BlockTypes.Char
    block_description: str = "A single character inside a span."

    text: str
    idx: int
