# DocLayout extraction benchmark

Install DocLayout using the [README instructions](../README.md#installation).
The benchmark scripts run from a clone; the installed `doclayout` command is
covered in the [CLI guide](../docs/usage.md#command-line-conversion).

DocLayout uses GPT-6 Sol for every page. This harness evaluates the current
application against a local olmOCR-bench dataset. Its results do not establish
general accuracy or local GPU throughput.

Run an evaluation with a page limit against a local olmOCR-bench directory:

```powershell
uv run python benchmarks/inference.py --bench-dir tests/data/olmocr_bench --out conversion_results/bench --limit 3
```

This makes billable API requests using the configured
[credentials and endpoint](../docs/configuration.md#credentials-and-environment). Default: one worker, no extra refinement. Use `--use-llm`
for refinement or `--workers` for additional processes. The model is fixed to
gpt-6-sol. `--raw` disables the existing olmOCR output normalization.

The harness extracts each page separately and writes a Markdown file. It records
failures in `latency.jsonl`, preserves prior page output when a request fails,
and exits with a nonzero status if any request fails.
Existing nonempty outputs are skipped. Timing includes API latency and rendering;
it is not a local GPU speed measurement. The harness preserves the olmOCR naming
scheme for use with its external evaluator. Competitor scripts run independently.

See [validation notes](../docs/gpt6-validation.md) for the three-page smoke result.

See [development checks](../docs/development.md#offline-checks) for offline tests
and [live evaluation](../docs/development.md#live-evaluation) for the explicit,
billable fixture-test command.

The three vendored PDFs cover selected reading-order, small-text, and
header/footer rules. They cover only part of the benchmark. Preserve the
[fixture attribution](../tests/data/olmocr_bench/README.md) when redistributing them.
See the [architecture guide](../docs/architecture.md) for the extraction path and
the [configuration guide](../docs/configuration.md) for application settings.
