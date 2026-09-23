# Optional local olmOCR-bench pages

This guide describes three single-page PDFs from
[olmOCR-bench](https://huggingface.co/datasets/allenai/olmOCR-bench)
(allenai, Apache-2.0) and the benchmark tests that apply to them. The PDFs and
JSONL records are local-only and excluded from fresh clones and package builds.
Existing local copies can remain here. `tests/converters/test_olmocr_bench.py`
converts each page and checks its local rules.

## Local setup

Obtain the benchmark data separately and keep it in an ignored folder or outside
the repository. The test expects a `pdfs/` directory and a `tests.jsonl` manifest.
Each JSONL record needs `pdf` (a path relative to `pdfs/`), `type`, and the
corresponding rule fields: `text` for present/absent or `before` and `after` for
order. Baseline rules need no additional text fields.

By default, the integration test uses this directory. To use another location:

```powershell
$env:DOCLAYOUT_BENCH_DIR = "D:\datasets\olmocr-bench"
uv run --no-sync pytest tests/converters/test_olmocr_bench.py --run-integration
```

Missing data is skipped before creating an API client. Offline tests generate
their own temporary documents and need no downloaded input files.

## Original three-page sample

| local file | source (olmOCR-bench `pdfs/`) | tests |
|---|---|---|
| `pdfs/multi_column_page1.pdf` | `multi_column/0005784d0d255f6652180433936fa2998188_page_1_pg1.pdf` | 5 × order (reading order) |
| `pdfs/long_tiny_text_pg36.pdf` | `long_tiny_text/11_pg36_pg1.pdf` | 4 × present (small-text OCR) |
| `pdfs/headers_footers_page1.pdf` | `headers_footers/4b91e05fb0fe865391f0f25c41a83c9c5fd37c08_page_1.pdf` | 4 × absent (header/footer stripping) + 1 × baseline |

`tests.jsonl` holds one record per test; each record's `source` field records the
original benchmark PDF path. Only the `present`/`absent`/`order`/`baseline` rule
types are supported. The `table`/`math` types need olmOCR-bench's own KaTeX +
table-parsing checker, which is not reimplemented here.

These pages check a small sample. They cannot establish a complete benchmark score.
See the [dated validation report](../../../docs/gpt6-validation.md) for observed
results and the header/footer limitation, and [live evaluation instructions](../../../docs/development.md#live-evaluation)
for running the fixture tests. Default tests skip live inference.
To expand the evaluation, use the [benchmark harness](../../../benchmarks/README.md)
with the complete dataset. Keep original source paths and rules intact when
updating these fixtures.
