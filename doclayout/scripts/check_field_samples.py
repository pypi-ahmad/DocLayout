"""Explicit, billable smoke test for the four user-approved masked samples."""

import argparse
import json
from pathlib import Path

from doclayout.field_store import FieldStore, atomic_write, storage_root
from doclayout.fields import ground_records, load_definition
from doclayout.models import create_model_dict, shutdown_models
from doclayout.ui.batch import process_file

SAMPLES = (
    ("Masked BadgeCare Plus_1.pdf", "0-1"),
    ("Masked Amerigroup_1.pdf", "0-1"),
    ("Masked_Amerigroup_RealSolutions_1.pdf", "1-2"),
    ("Masked_Amerigroup_RealSolutions_2.pdf", "0-0"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=storage_root())
    parser.add_argument(
        "--revalidate-saved",
        action="store_true",
        help="Recheck saved evidence locally; makes no model calls.",
    )
    args = parser.parse_args()
    definition = load_definition(enabled=False)
    if args.revalidate_saved:
        store = FieldStore(args.output_dir)
        seen = set()
        summaries = []
        validation_reasons = {
            "Evidence quote/path does not match source Markdown.",
            "Quote verified, but PDF block mapping is missing or ambiguous.",
            "Source block geometry is invalid.",
            "Populated field has no verified source quote.",
        }
        for saved in store.runs():
            if saved["filename"] not in dict(SAMPLES) or saved["document_id"] in seen:
                continue
            seen.add(saved["document_id"])
            if saved["definition_version"] != definition.version:
                raise ValueError(
                    "Saved prompt version differs; do not relabel historical extraction."
                )
            run = store.run(saved["id"])
            directory = store.document_dir(saved["document_id"])
            data = {
                "records": [
                    {
                        "fields": r["fields"],
                        "evidence": [
                            {"field_path": e["field_path"], "quote": e["quote"]}
                            for e in r["evidence"]
                        ],
                        "issues": [
                            i
                            for i in r["issues"]
                            if i["reason"] not in validation_reasons
                        ],
                    }
                    for r in run["records"]
                ],
                "document_issues": run["result"].get("document_issues", []),
            }
            data = ground_records(
                data,
                (directory / "raw.md").read_text("utf-8"),
                json.loads((directory / "chunks.json").read_text("utf-8")),
            )
            data.update(
                classification=run["result"]["classification"],
                revalidated_from=saved["id"],
                status="success"
                if data["records"]
                and all(r["status"] == "success" for r in data["records"])
                else "needs_review",
            )
            new_id = store.save_result(saved["document_id"], definition, data, [])
            summary = {
                "filename": saved["filename"],
                "run_id": new_id,
                "status": data["status"],
                "records": len(data["records"]),
                "review_issues": sum(len(r["issues"]) for r in data["records"]),
                "verified_quotes": sum(
                    e["verified"] for r in data["records"] for e in r["evidence"]
                ),
                "mapped_quotes": sum(
                    bool(e["locations"]) for r in data["records"] for e in r["evidence"]
                ),
            }
            summaries.append(summary)
            print(json.dumps(summary), flush=True)
        atomic_write(
            args.output_dir / "grounding-report.json", json.dumps(summaries, indent=2)
        )
        return
    # Validate every source before making any billable requests.
    sources = [
        (name, pages, (args.input_dir / name).read_bytes()) for name, pages in SAMPLES
    ]
    models = create_model_dict()
    summaries = []
    try:
        for name, pages, data in sources:
            receipt = process_file(
                name,
                data,
                {"page_range": pages, "use_llm": False},
                models,
                definition,
                root=args.output_dir,
            )
            summary = {k: v for k, v in receipt.items() if k != "usage"}
            summary["selected_pages_zero_based"] = pages
            summary["usage"] = receipt["usage"]
            if "run_id" in receipt:
                run = FieldStore(args.output_dir).run(receipt["run_id"])
                summary["records"] = len(run["records"])
                summary["review_issues"] = sum(len(r["issues"]) for r in run["records"])
            summaries.append(summary)
            atomic_write(
                args.output_dir / "smoke-report.json", json.dumps(summaries, indent=2)
            )
            print(
                json.dumps({k: v for k, v in summary.items() if k != "usage"}),
                flush=True,
            )
    finally:
        shutdown_models(models)


if __name__ == "__main__":
    main()
