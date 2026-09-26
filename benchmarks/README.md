# DocLayout extraction benchmark

Install DocLayout using the [README instructions](../README.md#installation).
The benchmark scripts run from a clone; the installed `doclayout` command is
covered in the [CLI guide](../docs/usage.md#command-line-conversion).

DocLayout uses GPT-6 Sol for every page. This harness runs it against a local
olmOCR-bench dataset. The results cover only the documents evaluated.

Obtain the dataset separately; input documents and benchmark records are not
distributed with DocLayout. Run an evaluation against your local dataset:

```powershell
uv run --extra layout python benchmarks/inference.py --bench-dir D:\datasets\olmocr-bench --out conversion_results/bench --limit 3
```

This makes billable API requests through the configured
[endpoint](../docs/configuration.md#credentials-and-environment). It uses one
worker and no extra refinement by default. Add `--use-llm` for refinement or
`--workers` for more processes. The model is fixed to gpt-6-sol. `--raw`
disables olmOCR output normalization.
The harness uses `PdfConverter`, so each page attempts V3 guidance. An absent
matching policy retains Sol geometry/order; V3 runtime failure also retains Sol
extraction. Such fallback is a successful conversion, not a benchmark failure.
Keep the runtime warnings when evaluating results: `latency.jsonl` does not store
V3 provider or alignment diagnostics. Use a normal JSON/metadata export when
those details are needed.

The harness extracts each page separately and writes a Markdown file. It records
failures in `latency.jsonl`, preserves prior page output when a request fails,
and exits with a nonzero status if any request fails.
Existing outputs larger than 10 bytes are skipped. Timing includes local layout
work, any first-use initialization/download, API latency, and rendering, so it
cannot isolate GPU speed. Each worker owns a separate lazy model runtime. The harness preserves olmOCR filenames for
its external evaluator. Competitor scripts run independently.

See [validation notes](../docs/gpt6-validation.md) for the three-page smoke result.

See [development checks](../docs/development.md#offline-checks) for offline tests
and [live evaluation](../docs/development.md#live-evaluation) for the explicit,
billable fixture-test command.

The original three-page sample covers selected reading-order, small-text, and
header/footer rules. These cover only part of the benchmark. Preserve the
[fixture attribution](../tests/data/olmocr_bench/README.md) when redistributing them.
See the [architecture guide](../docs/architecture.md) for the extraction path and
the [configuration guide](../docs/configuration.md) for application settings.
