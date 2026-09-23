# Vendored olmOCR-bench pages

This directory contains three single-page PDFs from
[olmOCR-bench](https://huggingface.co/datasets/allenai/olmOCR-bench)
(allenai, Apache-2.0) and the benchmark tests that apply to them.
`tests/converters/test_olmocr_bench.py` uses them for an end-to-end quality
integration test: DocLayout converts each page, then checks that all vendored rules pass.

| local file | source (olmOCR-bench `pdfs/`) | tests |
|---|---|---|
| `pdfs/multi_column_page1.pdf` | `multi_column/0005784d0d255f6652180433936fa2998188_page_1_pg1.pdf` | 5 × order (reading order) |
| `pdfs/long_tiny_text_pg36.pdf` | `long_tiny_text/11_pg36_pg1.pdf` | 4 × present (small-text OCR) |
| `pdfs/headers_footers_page1.pdf` | `headers_footers/4b91e05fb0fe865391f0f25c41a83c9c5fd37c08_page_1.pdf` | 4 × absent (header/footer stripping) + 1 × baseline |

`tests.jsonl` holds one record per test; each record's `source` field records the
original benchmark PDF path. Only the `present`/`absent`/`order`/`baseline` rule
types are vendored. The `table`/`math` types need olmOCR-bench's own KaTeX +
table-parsing checker, which is not reimplemented here.

These pages check for regressions on a small sample. They cannot establish a
complete benchmark score.
See the [dated validation report](../../../docs/gpt6-validation.md) for observed
results and the header/footer limitation, and [live evaluation instructions](../../../docs/development.md#live-evaluation)
for running the fixture tests. Default tests skip live inference.
To expand the evaluation, use the [benchmark harness](../../../benchmarks/README.md)
with the complete dataset. Keep original source paths and rules intact when
updating these fixtures.
