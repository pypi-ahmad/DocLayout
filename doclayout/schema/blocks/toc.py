# Modified for DocLayout; see NOTICE for a summary of changes.
from doclayout.schema import BlockTypes
from doclayout.schema.blocks.basetable import BaseTable


class TableOfContents(BaseTable):
    block_type: str = BlockTypes.TableOfContents
    block_description: str = "A table of contents."
