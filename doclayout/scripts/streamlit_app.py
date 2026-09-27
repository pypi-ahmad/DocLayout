"""DocLayout navigation; page changes never trigger model calls."""

import os
from pathlib import Path

import streamlit as st

os.environ["IN_STREAMLIT"] = "true"
st.set_page_config(page_title="DocLayout", layout="wide")
st.session_state.setdefault("session_usage", [])
pages = Path(__file__).resolve().parent / "app_pages"
navigation_pages = [
    st.Page(pages / "convert.py", title="Convert documents", default=True),
    st.Page(pages / "review.py", title="Extracted information"),
]
current_page = st.navigation(  # ty: ignore[call-non-callable] - Streamlit re-exports the public function
    navigation_pages, position="hidden"
)
for page in navigation_pages:
    if st.sidebar.button(
        page.title,
        key=f"navigation_{page.url_path}",
        type="primary" if page == current_page else "secondary",
        width="stretch",
    ):
        st.switch_page(page)
current_page.run()
