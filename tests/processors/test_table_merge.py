from unittest.mock import Mock


from doclayout.processors.llm.llm_table_merge import LLMTableMergeProcessor
from doclayout.schema import BlockTypes


def test_llm_table_processor_nomerge(pdf_document):
    mock_cls = Mock()
    mock_cls.return_value = {"merge": "true", "direction": "right"}

    tables = pdf_document.contained_blocks((BlockTypes.Table,))
    assert len(tables) == 2

    processor = LLMTableMergeProcessor(mock_cls, {"use_llm": True})
    processor(pdf_document)

    tables = pdf_document.contained_blocks((BlockTypes.Table,))
    assert len(tables) == 2
