# Modified for DocLayout; see NOTICE for a summary of changes.
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import Block


class PageHeader(Block):
    block_type: BlockTypes = BlockTypes.PageHeader
    block_description: str = (
        "Text that appears at the top of a page, like a page title."
    )
    replace_output_newlines: bool = True
    ignore_for_output: bool = False
    html: str | None = None

    def assemble_html(self, document, child_blocks, parent_structure, block_config):
        from doclayout.layout import visible_block

        if not visible_block(self, block_config):
            return ""
        if self.html:
            return self.html

        return super().assemble_html(
            document, child_blocks, parent_structure, block_config
        )
