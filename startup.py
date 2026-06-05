import os

import streamlit as st

st.set_page_config(
    page_title="Databricks + Fabric Expert Assistant" if os.getenv("ENABLE_FABRIC", "false").lower() == "true" else "Databricks Expert Assistant",
    page_icon="🌐",
    layout="wide",
)

from app.main import run

run()
