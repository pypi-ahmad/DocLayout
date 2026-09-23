# Modified for DocLayout; see NOTICE for a summary of changes.
from doclayout.schema import BlockTypes
from doclayout.schema.blocks.basetable import BaseTable


class Table(BaseTable):
    block_type: BlockTypes = BlockTypes.Table
    block_description: str = "A table of data, like a results table.  It will be in a tabular format."
