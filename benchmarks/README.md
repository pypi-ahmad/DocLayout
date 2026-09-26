# DocLayout extraction benchmark

Install DocLayout using the [README instructions](../README.md#installation).
The benchmark scripts run from a clone; the installed `doclayout` command is
covered in the [CLI guide](../docs/usage.md#command-line-conversion).

DocLayout uses GPT-6 Sol for every page. This harness runs it against a local
olmOCR-bench dataset. New conversions in this checkout attempt V3 first, with Sol
fallback when layout is unavailable. Each worker process owns its own layout
engine. The results cover only the documents evaluated.

This benchmark measures conversion only. It does not measure Luna classification,
authorization-field accuracy, or PDF evidence mapping. The separate
[field validation notes](../docs/field-extraction.md#verification) report the bounded
downstream smoke tests and their review limitations.

Obtain the dataset separately; input documents and benchmark records are not
distributed with DocLayout. Run an evaluation against your local dataset:

```powershell
uv run python benchmarks/inference.py --bench-dir D:\datasets\olmocr-bench --out conversion_results/bench --limit 3
```

This makes billable API requests through the configured
[endpoint](../docs/configuration.md#credentials-and-environment). It uses one
worker and no extra refinement by default. Add `--use-llm` for refinement or
`--workers` for more processes. The model is fixed to gpt-6-sol. `--raw`
disables olmOCR output normalization.

The harness extracts each page separately and writes a Markdown file. It records
failures in `latency.jsonl`, preserves prior page output when a request fails,
and exits with a nonzero status if any request fails.
Existing outputs larger than 10 bytes are skipped without checking the conversion
pipeline fingerprint. Use a new output directory when comparing pipeline versions;
do not interpret an old Markdown file as a fresh V3 result. The latency log names
Sol but does not record the full layout provenance or actual device. Timing includes
layout preparation/inference, API latency, and rendering, so it cannot measure
local GPU speed. The harness preserves olmOCR filenames for
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
