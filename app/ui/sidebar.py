import uuid

import streamlit as st

import app.session as session_module
from app.clients import CLIENT_INIT_ERROR
from app.config import ENABLE_FABRIC, ENABLE_POWERBI, FINAL_CONTEXT_K, REASONING_MODEL, REASONING_MODEL_OPTIONS
from app.rag import render_sidebar_status_card
from app.session import (
    CHAT_INPUT_FILE_SUPPORT,
    queue_answer_mode_regeneration,
    queue_product_route_regeneration,
    queue_reasoning_model_regeneration,
)
from app.ui.styles import APP_BUILD_MARKER


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
                "📎 Attach screenshot/file for next message",
                type=["png", "jpg", "jpeg", "txt", "log", "json", "sql", "py", "yml", "yaml", "md", "csv"],
                accept_multiple_files=True,
            )

            if session_module.sidebar_uploaded_file:
                st.info(f"{len(session_module.sidebar_uploaded_file)} attachment{'s' if len(session_module.sidebar_uploaded_file) != 1 else ''} ready for next message.")

        if st.button("Clear chat", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["session_id"] = str(uuid.uuid4())
            st.session_state["show_feedback_details"] = False

            for key in [
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
                "_ui_product_mode",
                "_ui_answer_mode",
                "_ui_context_k",
            ]:
                if key in st.session_state:
                    del st.session_state[key]

            st.rerun()

        with st.expander("Build info", expanded=False):
            st.caption(f"Build: `{APP_BUILD_MARKER}`")
            st.caption(f"Reasoning model: `{st.session_state.get('reasoning_model_endpoint', REASONING_MODEL)}`")


    st.session_state["_ui_product_mode"] = product_mode
    st.session_state["_ui_answer_mode"] = answer_mode
    st.session_state["_ui_context_k"] = k
