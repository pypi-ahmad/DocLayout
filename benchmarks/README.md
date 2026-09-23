# DocLayout extraction benchmark

DocLayout uses GPT-6 Sol for every page. This harness measures the current
application against a local olmOCR-bench dataset; results are not a claim of
general accuracy or local GPU throughput.

Run a bounded evaluation against a local olmOCR-bench directory:

```powershell
uv run python benchmarks/inference.py --bench-dir tests/data/olmocr_bench --out conversion_results/bench --limit 3
```

This makes billable API requests using `OPENAI_API_KEY` and optional
`OPENAI_BASE_URL`. Default: one worker, no extra refinement. Use `--use-llm`
for refinement or `--workers` for additional processes. The model is fixed to
gpt-6-sol. `--raw` disables the existing olmOCR output normalization.

Each page gets its own extraction and Markdown file. Failures are recorded in
`latency.jsonl`, do not overwrite prior page output, and produce a nonzero exit.
Existing nonempty outputs are skipped. Timing includes API latency and rendering;
it is not a local GPU speed measurement. The harness preserves the olmOCR naming
scheme for use with its external evaluator. Competitor scripts run independently.

See [validation notes](../docs/gpt6-validation.md) for the three-page smoke result.

Default project tests use mocked model calls. Live fixture tests are a separate,
billable check:

```powershell
uv run pytest tests/converters/test_olmocr_bench.py --run-integration
```

The three vendored PDFs exercise only selected reading-order, small-text, and
header/footer rules. They do not cover the complete benchmark. Preserve the
[fixture attribution](../tests/data/olmocr_bench/README.md) when redistributing them.
See the [architecture guide](../docs/architecture.md) for the extraction path and
the [usage guide](../docs/usage.md) for configuration.
