"""Readable, read-only presentation of saved extraction values."""

import json
from datetime import datetime
from pathlib import Path

import streamlit as st


def field_label(path):
    """Return a readable label while retaining the original path as an identifier."""
    labels = {
        "request_date": "Requested service date",
        "requested_service_dates": "Service dates",
        "requested_units_or_visits": "Units / visits",
        "scheduled_service_datetime": "Scheduled date and time",
        "expedited_requested": "Expedited request",
        "priority_evidence": "Supporting priority text",
    }
    parts = []
    for part in path.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if part.isdigit():
            parts.append(str(int(part) + 1))
        else:
            words = part.replace("_", " ").split()
            label = " ".join(
                w.upper() if w.lower() in {"id", "npi"} else w for w in words
            )
            parts.append(labels.get(part, label[:1].upper() + label[1:]))
    return " · ".join(parts) or "Request"


def status_label(status):
    """Describe processing state without claiming clinical verification."""
    return {
        "success": "Ready",
        "needs_review": "Needs review",
        "failed": "Could not extract information",
        "fallout": "Could not classify",
        "classified_no_extraction": "Not selected for extraction",
    }.get(status, field_label(status))


def saved_result_label(run):
    """Format the saved timestamp without changing its timezone."""
    try:
        stamp = datetime.fromisoformat(run["created_at"])
        date = stamp.strftime("%d %b %Y, %H:%M:%S %Z").strip()
    except ValueError:
        date = run["created_at"]
    return f"{run['filename']} · {date} · {status_label(run['status'])}"


def request_label(record, index):
    """Identify requests by their saved member name, with a numbered fallback."""
    member = record["fields"].get("member") or {}
    name = " ".join(
        str(member[k]) for k in ("first_name", "last_name") if member.get(k)
    )
    return f"Request {index + 1}" + (f" · {name}" if name else "")


def missing(value):
    """Treat empty information as missing, but preserve explicit false and zero."""
    if isinstance(value, dict):
        return all(missing(item) for item in value.values())
    if isinstance(value, list):
        return all(missing(item) for item in value)
    return value is None or (isinstance(value, str) and not value.strip())


def display_value(value):
    """Produce plain display text without coercing identifiers, dates, or codes."""
    if missing(value):
        return "Not found"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return "; ".join(display_value(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(
            f"{field_label(k)}: {display_value(v)}" for k, v in value.items()
        )
    return str(value)


def summary_sections(fields, show_missing=False):
    """Build display-only sections from the schema and saved values.

    The schema supplies ordering and missing-field names, never values. Unknown
    saved keys remain visible and an unavailable schema does not block browsing.
    """
    try:
        schema = json.loads(
            (
                Path(__file__).parents[1] / "prompts/fields/extraction.schema.json"
            ).read_text("utf-8")
        )["properties"]["records"]["items"]["properties"]["fields"]["properties"]
    except (OSError, ValueError, KeyError, TypeError):
        schema = {}
    groups = []
    combined = {
        "service_types": ("Service selections", ("service_types", "places_of_service")),
        "expedited_requested": (
            "Priority",
            ("expedited_requested", "priority_evidence"),
        ),
    }
    keys = list(dict.fromkeys([*schema, *fields]))
    consumed = set()
    for key in keys:
        if key in consumed:
            continue
        if key in combined:
            title, grouped = combined[key]
            values = {name: fields.get(name) for name in grouped}
            properties = {name: schema.get(name, {}) for name in grouped}
            consumed.update(grouped)
        else:
            title = field_label(key)
            values = fields.get(key)
            properties = schema.get(key, {}).get("properties", {})
        if not show_missing and missing(values):
            continue
        if (
            isinstance(values, list)
            and values
            and all(isinstance(item, dict) for item in values)
        ):
            columns = list(
                dict.fromkeys(
                    [
                        *schema.get(key, {}).get("items", {}).get("properties", {}),
                        *(
                            name
                            for item in values
                            if isinstance(item, dict)
                            for name in item
                        ),
                    ]
                )
            )
            columns = [
                name
                for name in columns
                if show_missing or any(not missing(item.get(name)) for item in values)
            ]
            rows = [
                {
                    field_label(name): display_value(item.get(name))
                    if show_missing or not missing(item.get(name))
                    else ""
                    for name in columns
                }
                for item in values
            ]
            groups.append((title, rows, True))
        else:
            if not isinstance(values, dict):
                values = {} if properties else {key: values}
            rows = {
                field_label(name): display_value(values.get(name))
                for name in dict.fromkeys([*properties, *values])
                if show_missing or not missing(values.get(name))
            }
            groups.append((title, rows, False))
    return groups


def show_summary(record):
    """Render native sections and read-only tables, with missing values opt-in."""
    show_missing = st.toggle("Show missing information", key=f"missing_{record['id']}")
    if show_missing:
        st.caption(
            "Not found means no value was saved for this field; it is not automatically an error."
        )
    sections = summary_sections(record["fields"], show_missing)
    if not sections:
        st.info("No field values were found in this saved request.")
    for title, rows, table in sections:
        with st.container(border=True):
            st.subheader(title)
            if table:
                st.dataframe(rows, hide_index=True)
            else:
                with st.container(horizontal=True):
                    for label, value in rows.items():
                        with st.container(width="stretch" if len(rows) == 1 else 230):
                            if label != title:
                                st.caption(label)
                            st.text(value)
