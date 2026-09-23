"""Session cost display; rendering never makes API requests."""

import streamlit as st

from doclayout.usage import MODEL_RATES, cost_summary


def show_costs(container, entries):
    total = cost_summary(entries)
    with container.container():
        with st.expander("Session API cost"):
            label = (
                "Estimated total" if total["complete"] else "Known subtotal (partial)"
            )
            st.metric(label, f"${total['estimated_cost_usd']:.6f}")
            for model, label in (
                ("gpt-6-sol", "OCR + refinement"),
                ("gpt-6-luna", "Document chat"),
            ):
                summary = cost_summary(
                    [entry for entry in entries if entry.get("model") == model]
                )
                st.write(f"{label}: ${summary['estimated_cost_usd']:.6f}")
            if not total["complete"]:
                st.warning(
                    f"Usage unavailable for {total['unknown_requests']} request(s). Actual cost may be higher."
                )
            st.caption(
                "USD estimates from reported tokens and configured rates. Includes earlier runs and cleared chats in this browser session."
            )
            st.json(
                {
                    key: value
                    for key, value in total.items()
                    if key != "estimated_cost_usd"
                }
            )
            st.caption(
                "Rates per 1M tokens: input / cached input / cache writes / output"
            )
            for model, rates in MODEL_RATES.items():
                st.text(f"{model}: " + " / ".join(f"${rate}" for rate in rates))
