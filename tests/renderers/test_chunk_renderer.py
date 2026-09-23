from doclayout.renderers.chunk import ChunkRenderer


def test_chunk_renderer(pdf_document):
    output = ChunkRenderer()(pdf_document)
    assert len(output.blocks) == 14
    assert output.blocks[0].block_type == "SectionHeader"
    assert output.page_info[0]["bbox"]
    figures = [block for block in output.blocks if block.block_type == "Figure"]
    assert len(figures) == 2
    assert all(len(block.images) == 1 for block in figures)
