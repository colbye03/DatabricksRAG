import streamlit as st

from app.local_storage import inject_history_loader, render_history_bridge
from app.session import init_chat_state
from app.ui.chat import render_chat, render_feedback_widget
from app.ui.sidebar import render_sidebar
from app.ui.styles import APP_BUILD_MARKER, APP_CSS


def run():
    st.markdown(f"<style>{APP_CSS}</style>", unsafe_allow_html=True)
    render_history_bridge()
    inject_history_loader()
    init_chat_state()
    render_sidebar()
    render_chat()
    render_feedback_widget()
