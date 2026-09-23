"""Run a bounded, billable GPT-6 Sol evaluation on local PDFs."""

import argparse
import json
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from postprocess import postprocess

from doclayout.converters.pdf import PdfConverter
from doclayout.models import create_model_dict, shutdown_models


def work(task):
    pdf, pdf_root, output, refine, raw = task
    from doclayout.providers.pdf import PdfProvider

    records = []
    provider = PdfProvider(str(pdf))
    models = create_model_dict()
    try:
        for page_id in provider.page_range:
            relative = pdf.relative_to(pdf_root)
            target = output / relative.parent / f"{pdf.stem}_pg{page_id + 1}_repeat1.md"
            if target.exists() and target.stat().st_size > 10:
                continue
            start = time.monotonic()
            error, text = "", ""
            try:
                converter = PdfConverter(
                    models,
                    config={
                        "page_range": [page_id],
                        "use_llm": refine,
                        "disable_tqdm": True,
                        "extract_images": False,
                        "html_tables_in_markdown": True,
                    },
                )
                text = converter(str(pdf)).markdown
                if not raw:
                    text = postprocess(text)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            except Exception as exc:
                error = str(exc)
            records.append(
                {
                    "pdf": relative.as_posix(),
                    "page": page_id + 1,
                    "latency_ms": round((time.monotonic() - start) * 1000, 1),
                    "chars": len(text),
                    "error": error,
                    "model": "gpt-6-sol",
                }
            )
    finally:
        shutdown_models(models)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-subdir", default="pdfs")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args()
    if args.workers < 1 or args.limit < 0:
        parser.error("workers must be positive and limit nonnegative")
    root = args.bench_dir / args.source_subdir
    pdfs = sorted(root.rglob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        parser.error(f"No PDFs in {root}")
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = [(pdf, root, args.out, args.use_llm, args.raw) for pdf in pdfs]
    with ProcessPoolExecutor(
        max_workers=args.workers, mp_context=mp.get_context("spawn")
    ) as pool:
        results = [record for batch in pool.map(work, tasks) for record in batch]
    with (args.out / "latency.jsonl").open("w", encoding="utf-8") as stream:
        for record in results:
            stream.write(json.dumps(record) + "\n")
    failures = sum(bool(record["error"]) for record in results)
    print(f"{len(results)} pages evaluated; {failures} failed.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
