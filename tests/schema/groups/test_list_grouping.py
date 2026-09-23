from doclayout.builders.structure import StructureBuilder
from doclayout.schema import BlockTypes


def test_html_list_preserved(pdf_document):
    StructureBuilder()(pdf_document)
    groups = pdf_document.contained_blocks((BlockTypes.ListGroup,))
    assert len(groups) == 2
    assert all(
        group.html == "<ul><li>First</li><li>Second</li></ul>" for group in groups
    )
