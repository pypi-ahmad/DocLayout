# Modified for DocLayout; see NOTICE for a summary of changes.
"""Session-based DocLayout workbench. Only explicit submits call models."""

import hashlib
from pathlib import Path

import streamlit as st

from doclayout.field_store import FieldStore
from doclayout.fields import load_definition
from doclayout.filenames import export_filename
from doclayout.layout import get_layout_engine
from doclayout.scripts.common import load_models, parse_args
from doclayout.settings import settings
from doclayout.ui.batch import (
    layout_readiness,
    layout_summary,
    load_conversion,
    process_batch,
)
from doclayout.ui.chat import answer_document_question
from doclayout.ui.clipboard import copy_buttons
from doclayout.ui.costs import show_costs
from doclayout.ui.documents import page_range, prepare_upload, preview
from doclayout.ui.exports import (
    image_bytes,
    markdown_preview,
)
from doclayout.ui.field_summary import status_label

st.title("DocLayout")
st.caption("From scans and images to structured Markdown.")
layout_status = st.empty()


def show_layout_status(status):
    """Display safe readiness on the Streamlit thread, without loading weights."""
    if status.startswith("Sol fallback"):
        layout_status.warning(status)
    else:
        layout_status.caption(status)


show_layout_status(layout_readiness(get_layout_engine()))
session_usage = st.session_state.setdefault("session_usage", [])
cost_panel = st.sidebar.empty()
show_costs(cost_panel, session_usage)
files = st.sidebar.file_uploader(
    "PDF, document, or image file",
    type=["pdf", "png", "jpg", "jpeg", "gif", "pptx", "docx", "xlsx", "html", "epub"],
    max_upload_size=settings.DOCLAYOUT_MAX_FILE_MIB,
    accept_multiple_files=True,
)
if not files:
    for key in (
        "upload_id",
        "upload",
        "scope",
        "result",
        "chat",
        "chat_usage",
        "batch_receipts",
        "result_document",
    ):
        st.session_state.pop(key, None)
    st.info(
        "Upload documents to begin, or open Extracted information for saved results."
    )
    st.stop()
multiple = len(files) > 1
uploaded = files[0]
upload_id = hashlib.sha256(
    b"".join(hashlib.sha256(f.getvalue() + f.name.encode()).digest() for f in files)
).hexdigest()
if st.session_state.get("upload_id") != upload_id:
    for key in (
        "result",
        "chat",
        "chat_usage",
        "start",
        "end",
        "preview_page",
        "scope",
        "upload",
        "batch_receipts",
        "result_document",
    ):
        st.session_state.pop(key, None)
    st.session_state.upload_id = upload_id
upload = None
start = end = 1
if not multiple:
    if "upload" not in st.session_state:
        try:
            st.session_state.upload = prepare_upload(uploaded.getvalue(), uploaded.name)
        except Exception:  # noqa: BLE001 - isolate document failures without exposing source data
            st.error(
                "Could not prepare this document. Check file limits and format dependencies."
            )
            st.stop()
    upload = st.session_state.upload
    st.sidebar.caption(f"{upload.count} page(s) · Pages are numbered from 1")
    start = st.sidebar.number_input(
        "Start page", min_value=1, max_value=upload.count, value=1, key="start"
    )
    end = st.sidebar.number_input(
        "End page", min_value=1, max_value=upload.count, value=upload.count, key="end"
    )
else:
    st.sidebar.caption(f"{len(files)} files · All pages · Three files active at once")
refine = st.sidebar.checkbox(
    "Extra refinement", help="Additional GPT-6 Sol requests after OCR"
)
headers = st.sidebar.checkbox("Show page headers/footers")
debug = st.sidebar.checkbox("Debug", help="Show result metadata and raw output")
options = {
    **parse_args(),
    "page_range": None if multiple else f"{start - 1}-{end - 1}",
    "use_llm": refine,
    "keep_pageheader_in_output": headers,
    "keep_pagefooter_in_output": headers,
}
scope = (upload_id, start, end, refine, headers)
if st.session_state.get("scope") != scope:
    for key in ("result", "chat", "chat_usage", "batch_receipts", "result_document"):
        st.session_state.pop(key, None)
    st.session_state.scope = scope
valid = multiple or start <= end
if not valid:
    st.sidebar.error("End page must be at least Start page.")
if st.sidebar.button("Run DocLayout", type="primary", disabled=not valid):
    try:
        definition = load_definition()
        st.session_state.batch_receipts = []
        progress = st.progress(0, text="Processing documents…")
        models = load_models()
        if not multiple:
            assert upload is not None
            options["page_range"] = page_range(start, end, upload.count)
        jobs = process_batch(
            [(f.name, f.getvalue()) for f in files],
            options,
            models,
            definition,
            prepared=None if multiple else upload,
            on_status=show_layout_status,
        )
        for receipt in jobs:
            st.session_state.batch_receipts.append(receipt)
            session_usage.extend(receipt["usage"])
            progress.progress(
                len(st.session_state.batch_receipts) / len(files),
                text=f"{len(st.session_state.batch_receipts)}/{len(files)} complete",
            )
            show_costs(cost_panel, session_usage)
        st.session_state.pop("result_document", None)
    except Exception as exc:  # noqa: BLE001 - isolate document failures without exposing source data
        st.error(
            f"Could not start processing ({type(exc).__name__}). Check definitions and API configuration."
        )
receipts = st.session_state.get("batch_receipts", [])
if receipts:
    st.dataframe(
        [
            {
                "File": r["filename"],
                "Status": status_label(r["status"]),
                "Details": r.get("error", ""),
            }
            for r in receipts
        ],
        hide_index=True,
    )
    store = FieldStore()
    available = [r for r in receipts if store.document(r["document_id"]) is not None]
    if available:
        selected_index = st.sidebar.selectbox(
            "Result document",
            range(len(available)),
            format_func=lambda index: available[index]["filename"],
        )
        selected = available[selected_index]
        if st.session_state.get("result_document") != selected["document_id"]:
            st.session_state.upload, st.session_state.result = load_conversion(
                store, selected["document_id"]
            )
            st.session_state.result_document = selected["document_id"]
            for key in ("preview_page", "chat", "chat_usage"):
                st.session_state.pop(key, None)
        upload = st.session_state.upload
        with st.container(border=True):
            st.text(selected["filename"])
            run_id = selected.get("run_id")
            if run_id and any(
                run["id"] == run_id and run["document_id"] == selected["document_id"]
                for run in store.runs()
            ):
                if st.button(
                    "View extracted information",
                    type="primary",
                    icon=":material/description:",
                ):
                    st.session_state.pending_review_run = run_id
                    st.switch_page(Path(__file__).with_name("review.py"))
                st.caption(
                    "Read the saved request details and check them against the source document."
                )
            else:
                st.info(
                    "No saved extraction is available for this result. Its conversion remains available below."
                )
if upload is None:
    st.info("Run the batch to create conversion and extraction results.")
    st.stop()

result = st.session_state.get("result")
if result:
    st.caption(f"Conversion pipeline: {result.get('pipeline', 'legacy-sol-only')}")
    summary = layout_summary(result["metadata"])
    if summary:
        st.caption(summary)
tabs = st.tabs(
    ["Input preview", "Markdown", "HTML", "Annotated", "JSON", "Chunks", "Chat"],
    key="result_tabs",
    on_change="rerun",
)
with tabs[0]:
    if tabs[0].open:
        page = st.number_input(
            "Preview page",
            min_value=1,
            max_value=upload.count,
            value=1,
            key="preview_page",
        )
        try:
            st.image(preview(upload, page - 1), width="stretch")
        except Exception:  # noqa: BLE001 - preview failure must not discard results
            st.warning("Preview is unavailable for this page.")
if not result:
    st.info("Select a page range and run DocLayout to create results.")
    st.stop()
st.sidebar.success(f"OCR complete · {len(result['document'].pages)} page(s)")
st.sidebar.download_button(
    "Download ZIP",
    result["zip"],
    export_filename(result["export_base"], "document.zip"),
    "application/zip",
    on_click="ignore",
)
with tabs[1]:
    if tabs[1].open:
        copy_buttons(
            data={"markdown": result["markdown"], "html": result["html"]},
            key="copy_markdown",
        )
        st.download_button(
            "Download Markdown",
            result["markdown"],
            export_filename(result["export_base"], "document.md"),
            "text/markdown",
            on_click="ignore",
        )
        view = st.segmented_control(
            "Markdown view", ["Rendered", "Raw"], default="Rendered"
        )
        if view == "Raw":
            st.code(result["markdown"], language="markdown", wrap_lines=True)
        else:
            st.html(markdown_preview(result["markdown"], result["images"]))
with tabs[2]:
    if tabs[2].open:
        copy_buttons(
            data={"text": result["html"], "label": "Copy HTML"}, key="copy_html"
        )
        st.download_button(
            "Download HTML",
            result["html"],
            export_filename(result["export_base"], "document.html"),
            "text/html",
            on_click="ignore",
        )
        st.iframe(result["html"], height=750)
with tabs[3]:
    if tabs[3].open:
        annotated = result["annotations"]
        st.caption(
            f"Rectangular block bounds · {annotated['drawn']} drawn · {annotated['skipped']} invalid boxes skipped"
        )
        st.download_button(
            "Download annotated PDF",
            annotated["pdf"],
            export_filename(result["export_base"], "annotated.pdf"),
            "application/pdf",
            on_click="ignore",
        )
        selected = st.selectbox("Annotated page", list(annotated["pages"]))
        st.image(annotated["pages"][selected], width="stretch")
        st.download_button(
            "Download page PNG",
            image_bytes(annotated["pages"][selected]),
            export_filename(result["export_base"], f"page-{selected}.png"),
            "image/png",
            on_click="ignore",
        )
for tab, field, label in ((tabs[4], "json", "JSON"), (tabs[5], "chunks", "Chunks")):
    with tab:
        if tab.open:
            copy_buttons(
                data={"text": result[field], "label": f"Copy {label}"},
                key=f"copy_{field}",
            )
            st.download_button(
                f"Download {label}",
                result[field],
                export_filename(
                    result["export_base"],
                    "document.json" if field == "json" else "chunks.json",
                ),
                "application/json",
                on_click="ignore",
            )
            st.json(result[field])
with tabs[6]:
    if tabs[6].open:
        st.caption(
            "GPT-6 Luna · Answers checked against parsed pages · Citations use original page numbers"
        )
        if st.button("Clear chat"):
            st.session_state.chat = []
            st.session_state.chat_usage = []
        history = st.session_state.setdefault("chat", [])
        for turn in history:
            with st.chat_message("user"):
                st.text(turn["question"])
            with st.chat_message("assistant"):
                st.text(turn["answer"])
        question = st.chat_input(
            "Ask about the parsed pages", max_chars=2000, disabled=not result["pages"]
        )
        if question:
            with st.chat_message("user"):
                st.text(question)
            with st.chat_message("assistant"), st.spinner("Checking the document…"):
                answer = answer_document_question(result["pages"], question, history)
                st.text(answer.answer)
            history.append(
                {"question": question, "answer": answer.answer, "status": answer.status}
            )
            st.session_state.setdefault("chat_usage", []).extend(answer.usage)
            session_usage.extend(answer.usage)
            show_costs(cost_panel, session_usage)
        with st.expander("Chat usage"):
            st.json(st.session_state.get("chat_usage", []))
if debug:
    with st.expander("Debug: metadata and raw Markdown"):
        st.json(result["metadata"])
        st.code(result["markdown"], language="markdown", wrap_lines=True)
