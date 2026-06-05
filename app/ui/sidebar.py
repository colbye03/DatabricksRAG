import streamlit as st

import app.session as session_module
from app.clients import CLIENT_INIT_ERROR
from app.config import ENABLE_FABRIC, ENABLE_POWERBI, FINAL_CONTEXT_K, REASONING_MODEL, REASONING_MODEL_OPTIONS
from app.local_storage import (
    BRIDGE_KEY,
    SESSIONS_BRIDGE_KEY,
    clear_current_chat,
    format_chat_session_label,
    get_chat_sessions_for_sidebar,
    start_new_chat,
    switch_chat_session,
)
from app.rag import render_sidebar_status_card
from app.session import (
    CHAT_INPUT_FILE_SUPPORT,
    queue_answer_mode_regeneration,
    queue_product_route_regeneration,
    queue_reasoning_model_regeneration,
)
from app.ui.styles import APP_BUILD_MARKER


CHAT_STATE_RESET_KEYS = [
    "last_question",
    "last_answer",
    "last_sources",
    "last_topic",
    "last_intent",
    "last_answer_mode",
    "last_product_route",
    "last_prompt_for_model",
    "last_attachment_context",
    "last_chat_history",
    "pending_answer_mode_regeneration",
    "last_answer_with_links",
    "last_example_selection",
    "pending_example_prompt",
    BRIDGE_KEY,
    SESSIONS_BRIDGE_KEY,
]


def _reset_chat_view_state():
    st.session_state["show_feedback_details"] = False
    for key in CHAT_STATE_RESET_KEYS:
        if key in st.session_state:
            del st.session_state[key]


def render_sidebar():
    session_module.sidebar_uploaded_file = None
    with st.sidebar:
        st.markdown(
            "<div style='font-size:0.78rem;color:#6b7280;margin-bottom:0.45rem;'>"
            "Created and maintained by EdColby"
            "</div>",
            unsafe_allow_html=True,
        )
        st.header("Assistant")
        render_sidebar_status_card()

        if CLIENT_INIT_ERROR:
            st.error("Databricks connection not ready")
            st.caption(CLIENT_INIT_ERROR)
        else:
            st.success("Connected to Databricks")

        st.subheader("Chats")
        if st.button("\u2795 New Chat", use_container_width=True):
            start_new_chat()
            _reset_chat_view_state()
            st.rerun()

        chat_sessions = get_chat_sessions_for_sidebar(limit=10)
        if chat_sessions:
            session_lookup = {session["id"]: session for session in chat_sessions}
            current_session_id = st.session_state.get("session_id", "")
            current_option = current_session_id if current_session_id in session_lookup else chat_sessions[0]["id"]
            if st.session_state.get("chat_session_selector") not in session_lookup:
                st.session_state["chat_session_selector"] = current_option

            selected_session_id = st.radio(
                "Previous chats",
                options=[session["id"] for session in chat_sessions],
                format_func=lambda session_id: format_chat_session_label(session_lookup[session_id]),
                key="chat_session_selector",
                label_visibility="collapsed",
            )

            if selected_session_id != current_session_id:
                if switch_chat_session(selected_session_id):
                    _reset_chat_view_state()
                    st.rerun()
        else:
            st.caption("No saved chats yet.")

        st.header("Settings")

        if ENABLE_FABRIC or ENABLE_POWERBI:
            product_route_options = ["Auto", "Databricks"]
            if ENABLE_FABRIC or ENABLE_POWERBI:
                product_route_options.append("Fabric / Power BI")
            if ENABLE_FABRIC or ENABLE_POWERBI:
                product_route_options.append("Compare / Better Together")
        else:
            product_route_options = ["Databricks"]

        if st.session_state.get("product_route_label") not in product_route_options:
            st.session_state["product_route_label"] = product_route_options[0]

        if ENABLE_FABRIC or ENABLE_POWERBI:
            route_panel = st.container(border=True)
            with route_panel:
                st.markdown(
                    """
                    <div class="route-callout route-callout-inner">
                      <div class="route-callout-title">
                        <span>Choose the product lens</span>
                        <span class="route-callout-pill">Route matters</span>
                      </div>
                      <div class="route-callout-text">
                                            Use this to keep answers in Databricks, Fabric, Power BI, or cross-product better-together mode.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                product_mode = st.selectbox(
                    "Product route",
                    product_route_options,
                    index=0,
                    key="product_route_label",
                    on_change=queue_product_route_regeneration,
                    help="Auto routes by question/screenshot signals. Force a product, or use Compare / Better Together for cross-product strategy.",
                )
                st.caption("Tip: use Fabric / Power BI for Microsoft analytics questions, or Compare / Better Together for Databricks positioning.")
        else:
            product_mode = st.selectbox(
                "Product route",
                product_route_options,
                index=0,
                key="product_route_label",
                on_change=queue_product_route_regeneration,
                help="Auto routes by question/screenshot signals. Force a product, or use Compare / Better Together for cross-product strategy.",
            )

        with st.expander("Advanced answer controls", expanded=False):
            answer_mode_label = st.selectbox(
                "Answer mode",
                [
                    "Auto",
                    "Customer Meeting Prep",
                    "Solution Architecture",
                    "Troubleshooting",
                    "Learning",
                    "Deep Explanation",
                    "Implementation / Step-by-step",
                    "Competitive / Customer Positioning",
                ],
                index=0,
                key="answer_mode_label",
                on_change=queue_answer_mode_regeneration,
                help="Leave on Auto unless you want to force a specific answer style.",
            )

            if st.session_state.get("reasoning_model_endpoint") not in REASONING_MODEL_OPTIONS:
                st.session_state["reasoning_model_endpoint"] = REASONING_MODEL

            selected_reasoning_model = st.selectbox(
                "Reasoning model",
                REASONING_MODEL_OPTIONS,
                index=REASONING_MODEL_OPTIONS.index(st.session_state["reasoning_model_endpoint"]),
                key="reasoning_model_endpoint",
                on_change=queue_reasoning_model_regeneration,
                help="Used for heavier answer modes and topics such as troubleshooting, architecture, implementation, Fabric mirroring, Unity Catalog, ADLS access, Spark performance, and learning.",
            )
            st.caption(f"Active reasoning model: `{selected_reasoning_model}`")

            k = st.slider(
                "Final context chunks",
                min_value=6,
                max_value=18,
                value=FINAL_CONTEXT_K,
                help="Advanced retrieval depth. Higher values can add more evidence but may make answers longer.",
            )

        ANSWER_MODE_MAP = {
            "Auto": "Auto",
            "Customer Meeting Prep": "Customer Meeting Prep",
            "Solution Architecture": "Solution Architecture",
            "Troubleshooting": "Troubleshooting Runbook",
            "Learning": "Learning",
            "Deep Explanation": "Deep Explanation",
            "Implementation / Step-by-step": "Implementation / Step-by-step",
            "Competitive / Customer Positioning": "Competitive / Customer Positioning",
        }

        answer_mode = ANSWER_MODE_MAP[answer_mode_label]

        if not CHAT_INPUT_FILE_SUPPORT:
            st.warning(
                "This Streamlit version does not support chat-bar file attachments. "
                "Use the sidebar attachment picker instead."
            )

            session_module.sidebar_uploaded_file = st.file_uploader(
                "\U0001F4CE Attach screenshot/file for next message",
                type=["png", "jpg", "jpeg", "txt", "log", "json", "sql", "py", "yml", "yaml", "md", "csv"],
                accept_multiple_files=True,
            )

            if session_module.sidebar_uploaded_file:
                st.info(f"{len(session_module.sidebar_uploaded_file)} attachment{'s' if len(session_module.sidebar_uploaded_file) != 1 else ''} ready for next message.")

        if st.button("Clear chat", use_container_width=True):
            clear_current_chat()
            _reset_chat_view_state()
            st.rerun()

        with st.expander("Build info", expanded=False):
            st.caption(f"Build: `{APP_BUILD_MARKER}`")
            st.caption(f"Reasoning model: `{st.session_state.get('reasoning_model_endpoint', REASONING_MODEL)}`")

    st.session_state["_ui_product_mode"] = product_mode
    st.session_state["_ui_answer_mode"] = answer_mode
    st.session_state["_ui_context_k"] = k
