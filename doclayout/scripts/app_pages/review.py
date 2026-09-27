"""Persistent field review and explicit extraction/export retries."""

import json

import streamlit as st

from doclayout.field_store import FieldStore
from doclayout.fields import load_definition
from doclayout.ui.batch import retry_fields
from doclayout.ui.costs import show_costs
from doclayout.ui.field_review import show_evidence
from doclayout.ui.field_summary import (
    field_label,
    request_label,
    saved_result_label,
    show_summary,
    status_label,
)

st.title("Extracted information")
st.caption(
    "View saved request details and compare them with the source document. Opening results does not run extraction again."
)
show_costs(st.sidebar.empty(), st.session_state.setdefault("session_usage", []))
store = FieldStore()
runs = store.runs()
if not runs:
    st.info("Process documents on Convert documents to create saved records.")
    st.stop()
choices = {r["id"]: r for r in runs}
if "pending_review_run" in st.session_state:
    pending = st.session_state.pop("pending_review_run")
    if pending in choices:
        st.session_state.saved_review_run = pending
    else:
        st.warning(
            "That saved result is no longer available. Select another result below."
        )
if st.session_state.get("saved_review_run") not in choices:
    st.session_state.pop("saved_review_run", None)
selection = st.selectbox(
    "Saved result",
    list(choices),
    key="saved_review_run",
    format_func=lambda key: saved_result_label(choices[key]),
)
run = store.run(selection)
document = store.document(run["document_id"])
st.badge(
    status_label(run["status"]),
    color="green" if run["status"] == "success" else "orange",
)
st.caption(
    "Extracted information is not independently verified. Check important details against the source."
)
record = None
if run["records"]:
    index = 0
    if len(run["records"]) > 1:
        index = st.selectbox(
            "Request",
            range(len(run["records"])),
            format_func=lambda index: request_label(run["records"][index], index),
            key=f"request_{run['id']}",
        )
    record = run["records"][index]
    st.subheader(request_label(record, index))
    if record["status"] != run["status"]:
        st.caption(f"Request status: {status_label(record['status'])}")
else:
    st.info(
        "This saved result contains no extracted requests. Its processing reasons are retained below."
    )

document_issues = run["result"].get("document_issues", [])
record_issues = record.get("issues", []) if record else []
if document_issues or record_issues:
    with st.expander("Items to check", expanded=True, icon=":material/warning:"):
        for issue in document_issues:
            st.text(issue)
        for issue in record_issues:
            st.text(f"{field_label(issue.get('field_path', ''))}: {issue['reason']}")

if record:
    summary, source = st.tabs(
        ["Summary", "Source document"],
        key=f"review_tabs_{run['id']}",
        on_change="rerun",
    )
    with summary:
        if summary.open:
            show_summary(record)
    with source:
        if source.open:
            try:
                show_evidence(store, document, record)
            except Exception:  # noqa: BLE001 - a failed preview must not discard saved values
                st.warning(
                    "Source preview unavailable. Saved information remains available in Summary and the JSON download."
                )
    st.download_button(
        "Download data (JSON)",
        json.dumps(record, ensure_ascii=False, indent=2),
        record["name"] + ".json",
        "application/json",
        on_click="ignore",
        icon=":material/download:",
    )

with st.expander("More actions"):
    st.caption(
        "Extract again makes a new API request using saved Markdown. It does not reconvert the source document."
    )
    if st.button("Extract again", disabled=document is None):
        try:
            with st.spinner("Extracting saved Markdown…"):
                new_id, usage = retry_fields(store, document["id"], load_definition())
            st.session_state.setdefault("session_usage", []).extend(usage)
            st.session_state.pending_review_run = new_id
            st.rerun()
        except Exception as exc:  # noqa: BLE001 - isolate document failures without exposing source data
            st.error(
                f"Extraction could not start ({type(exc).__name__}). Check definition files."
            )
    if run["result"].get("export_error"):
        st.warning(run["result"]["export_error"])
        if st.button("Retry JSON export"):
            error = store.export_run(run["id"])
            st.error(error) if error else st.success("JSON exports saved.")

with st.expander("Technical details"):
    st.json(
        {
            "run_id": run["id"],
            "document_id": run["document_id"],
            "definition_version": run["definition_version"],
            **run["result"],
            "record": record,
        }
    )
