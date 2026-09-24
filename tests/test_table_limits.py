"""Small policy-boundary regression cases; no model calls or stress inputs."""

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from doclayout import security
from doclayout.processors.llm.llm_table import LLMTableProcessor
from doclayout.processors.llm.llm_table_merge import LLMTableMergeProcessor
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.schema.extraction import sanitize_html
from doclayout.schema.polygon import PolygonBox
from doclayout.security import DocumentLimitError, check_table


@pytest.fixture
def small_policy(monkeypatch):
    monkeypatch.setattr(security, "MAX_TABLE_DIMENSION", 4)
    monkeypatch.setattr(security, "MAX_TABLE_CELLS", 8)


def table(body):
    return f"<table>{body}</table>"


@pytest.mark.parametrize("span", ["0", "-1", "+2", "1.5", "", "two", "２", "5"])
@pytest.mark.parametrize("attribute", ["rowspan", "colspan"])
def test_invalid_spans_fail_closed(small_policy, span, attribute):
    html = table(f'<tr><td {attribute}="{span}">A</td></tr>')
    with pytest.raises(DocumentLimitError):
        sanitize_html(html)


@pytest.mark.parametrize(
    "body",
    [
        "<tr><td>A</td></tr>" * 5,  # Row dimension.
        "<tr>" + "<td>A</td>" * 5 + "</tr>",  # Column dimension.
        '<tr><td colspan="3">A</td></tr>' * 3,  # Grid area.
        '<tr><td rowspan="3" colspan="3">A</td></tr>',  # Span work.
    ],
)
def test_shape_budgets_before_consumption(small_policy, body):
    html = table(body)
    consumers = [
        sanitize_html,
        MarkdownRenderer().md_cls.convert,
        MarkdownRenderer({"html_tables_in_markdown": True}).md_cls.convert,
        lambda value: LLMTableProcessor(None).parse_html_table(value, None, None),
    ]
    for consume in consumers:
        with pytest.raises(DocumentLimitError):
            consume(html)


def test_bounded_rowspan_shape_and_rendering(small_policy):
    html = table('<tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr>')
    assert check_table(BeautifulSoup(html, "html.parser")) == (2, 2)
    assert 'rowspan="2"' in sanitize_html(html)
    markdown = MarkdownRenderer().md_cls.convert(html)
    assert "| A | B |" in markdown
    assert "|   | C |" in markdown
    block = SimpleNamespace(polygon=PolygonBox.from_bbox([0, 0, 10, 10]))
    cells = LLMTableProcessor(None).parse_html_table(
        html, block, SimpleNamespace(page_id=0)
    )
    assert [(cell.row_id, cell.col_id) for cell in cells] == [(0, 0), (0, 1), (1, 1)]


def test_exact_grid_budget_and_missing_spans(small_policy):
    html = table('<tr><td colspan="4">A</td></tr><tr><td>B</td></tr>')
    assert check_table(BeautifulSoup(html, "html.parser")) == (2, 4)
    assert "A" in MarkdownRenderer().md_cls.convert(html)


def test_merged_tables_recheck_combined_budget(small_policy):
    first = table('<tr><td colspan="3">A</td></tr>' * 2)
    second = table('<tr><td colspan="3">B</td></tr>')
    with pytest.raises(DocumentLimitError):
        LLMTableMergeProcessor.join_html_tables(first, second)
    merged = LLMTableMergeProcessor.join_html_tables(second, second)
    assert check_table(BeautifulSoup(merged, "html.parser")) == (2, 3)
