# Modified for DocLayout; see NOTICE for a summary of changes.
"""Session-based DocLayout workbench. Only explicit submits call models."""

import hashlib
import os

import streamlit as st

from doclayout.credentials import CredentialsError
from doclayout.filenames import export_basename, export_filename, name_result
from doclayout.scripts.common import load_models, parse_args
from doclayout.ui.chat import answer_document_question
from doclayout.ui.clipboard import copy_buttons
from doclayout.ui.costs import show_costs
from doclayout.ui.documents import page_range, prepare_upload, preview, run_document
from doclayout.ui.exports import (
    annotations,
    image_bytes,
    markdown_html,
    markdown_preview,
    output_zip,
)

os.environ["IN_STREAMLIT"] = "true"
st.set_page_config(page_title="DocLayout", layout="wide")
st.title("DocLayout")
st.caption("From scans and images to structured Markdown.")
session_usage = st.session_state.setdefault("session_usage", [])
cost_panel = st.sidebar.empty()
show_costs(cost_panel, session_usage)
uploaded = st.sidebar.file_uploader(
    "PDF, document, or image file",
    type=["pdf", "png", "jpg", "jpeg", "gif", "pptx", "docx", "xlsx", "html", "epub"],
)
if uploaded is None:
    for key in ("upload_id", "upload", "scope", "result", "chat", "chat_usage"):
        st.session_state.pop(key, None)
    st.info("Upload a document to begin.")
    st.stop()

upload_id = hashlib.sha256(uploaded.getvalue() + uploaded.name.encode()).hexdigest()
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
        "upload_id",
    ):
        st.session_state.pop(key, None)
    try:
        with st.spinner("Preparing document…"):
            st.session_state.upload = prepare_upload(uploaded.getvalue(), uploaded.name)
        st.session_state.upload_id = upload_id
    except Exception:  # noqa: BLE001 - document errors may contain private paths
        st.error(
            "Could not prepare this document. Check the file and required document-format dependencies."
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
refine = st.sidebar.checkbox(
    "Extra refinement", help="Additional GPT-6 Sol requests after OCR"
)
headers = st.sidebar.checkbox("Show page headers/footers")
debug = st.sidebar.checkbox("Debug", help="Show result metadata and raw output")
options = {
    **parse_args(),
    "page_range": f"{start - 1}-{end - 1}",
    "use_llm": refine,
    "keep_pageheader_in_output": headers,
    "keep_pagefooter_in_output": headers,
}
scope = (upload_id, start, end, refine, headers)
if st.session_state.get("scope") != scope:
    for key in ("result", "chat", "chat_usage"):
        st.session_state.pop(key, None)
    st.session_state.scope = scope
valid = start <= end
if not valid:
    st.sidebar.error("End page must be at least Start page.")
if st.sidebar.button("Run DocLayout", type="primary", disabled=not valid):
    for key in ("result", "chat", "chat_usage"):
        st.session_state.pop(key, None)
    try:
        options["page_range"] = page_range(start, end, upload.count)
        with st.spinner("Extracting selected pages…"):
            result = run_document(
                upload, options, load_models(), usage_entries=session_usage
            )
            name_result(result, export_basename(uploaded.name))
            result["html"] = markdown_html(result["markdown"], result["images"])
            result["annotations"] = annotations(result["document"])
            result["zip"] = output_zip(result)
            st.session_state.result = result
    except CredentialsError as exc:
        st.error(str(exc))
    except Exception:  # noqa: BLE001 - do not disclose provider error payloads
        st.error(
            "Conversion failed. Check API availability, credentials, and the selected document. No result was retained."
        )
    finally:
        show_costs(cost_panel, session_usage)

result = st.session_state.get("result")
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
            st.markdown(markdown_preview(result["markdown"], result["images"]))
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
            f"Estimated OCR boxes · {annotated['drawn']} drawn · {annotated['skipped']} invalid boxes skipped"
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
