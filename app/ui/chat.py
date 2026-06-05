import streamlit as st

import app.session as session_module
from app.attachments import extract_text_from_attachment
from app.config import ENABLE_FABRIC, FEEDBACK_LOGGING_ENABLED, FINAL_CONTEXT_K, MAX_HISTORY_MESSAGES
from app.feedback import render_feedback_controls, render_shareable_report_button, save_chat_message, save_feedback
from app.local_storage import save_chat_to_local_storage
from app.rag import ask_databricks_sme, regenerate_last_answer
from app.routing import resolve_product_route
from app.session import (
    CHAT_INPUT_FILE_SUPPORT,
    EXAMPLE_PLACEHOLDER,
    get_recent_chat_history_before_current,
    normalize_chat_input,
    queue_selected_example_question,
    render_paste_screenshot_helper,
    render_scroll_to_latest_exchange_script,
)
from app.ui.components import (
    add_clickable_citations,
    render_evidence_summary,
    render_screenshot_triage_summary,
    render_source_list_expander,
)

def render_readme_panel():
    if ENABLE_FABRIC:
        readme_body = """
### What this app does

This assistant helps with Azure Databricks, Microsoft Fabric, and Power BI questions using product-aware retrieval, Databricks model serving, curated playbooks, citations, session context, screenshots/files, and a source browser.

Use it for:

- Troubleshooting Azure Databricks, Fabric, and Power BI issues
- Architecture decisions across Databricks, Fabric, OneLake, Unity Catalog, and Power BI semantic models
- Customer meeting prep and competitive positioning
- Step-by-step implementation planning
- Learning explanations backed by indexed documentation and internal playbooks

It is best for internal field and engineering prep. Review strategic customer-ready answers before sending them externally.

### How to use it

1. Pick a **Product route** in the sidebar, or leave it on **Auto**.
2. Pick an **Answer mode** only if you want a specific style, such as architecture, troubleshooting, or customer positioning.
3. Ask a specific question in the chat box.
4. Paste exact errors, UI text, table names, settings, workspace details, or customer context when available.
5. Attach screenshots, logs, SQL, config files, or notes when they matter.
6. Review the inline citations and the **Sources** expander under the answer.

### Product routes

| Route | Use when |
| --- | --- |
| **Auto** | You want the app to infer the right product from the question and recent chat. |
| **Databricks** | The question is mainly about Azure Databricks: workspaces, clusters, Unity Catalog, SQL warehouses, Delta, Lakeflow, model serving, Vector Search, networking, or storage access. |
| **Fabric / Power BI** | The question is mainly about Microsoft Fabric, OneLake, lakehouses, warehouses, pipelines, semantic models, Direct Lake, DirectQuery, Import mode, Power BI, DAX, or Power Query. |
| **Compare / Better Together** | The question crosses Databricks, Fabric, and Power BI, or you need architecture boundaries, customer positioning, competitive response, or better-together guidance. |

Follow-up questions stay in the current route unless you explicitly change the route or ask about another product.

### Answer modes

| Mode | Use when you want |
| --- | --- |
| **Auto** | The app to infer whether the request is troubleshooting, architecture, learning, meeting prep, implementation, or status-related. |
| **Customer Meeting Prep** | A customer-safe briefing, likely concerns, talk track, risks, objections, and follow-up actions. |
| **Solution Architecture** | Decision-grade architecture guidance with tradeoffs, governance boundaries, performance/cost implications, risks, and validation checks. |
| **Troubleshooting** | Ranked causes, exact evidence to collect, UI/log checks, isolation tests, fixes, and validation steps. |
| **Learning** | A teachable explanation with a mental model, practical example, role split, gotchas, and self-check. |
| **Deep Explanation** | More detail on internals, constraints, edge cases, and why the recommendation works. |
| **Implementation / Step-by-step** | Ordered build steps, prerequisites, permissions, validation, and common mistakes. |
| **Competitive / Customer Positioning** | Scenario readout, technical truth table, customer-ready response, meeting agenda, talk track, landmines, proof points, and next actions. |

### What makes a good question

Good prompts include the product, goal, symptom, and decision you need to make.

Examples:

- `Fabric / Power BI route, Solution Architecture mode: For Databricks Unity Catalog tables and a large Power BI audience, compare Direct Lake, Import, and DirectQuery. Include governance, cost, freshness, and validation.`
- `Databricks route, Troubleshooting mode: My cluster is stuck pending. Here is the event log error and the cluster policy name.`
- `Compare / Better Together route, Competitive / Customer Positioning mode: Databricks is challenging Power BI semantic models in a customer renewal. Help me prepare the response and who should join the call.`

### Attachments and screenshots

- You can attach screenshots, logs, SQL, JSON, YAML, Markdown, Python, CSV, or text files.
- Screenshots are triaged for visible error text, likely product area, severity, and first checks when screenshot OCR is configured.
- If the screenshot is unreadable, paste the visible error text directly into chat.

### Sources and citations

- Answers cite retrieved sources inline like `[1]`, `[2]`.
- Open the **Sources** expander under an answer to inspect what influenced the response.
- Curated playbooks are internal guidance. Official retrieved docs should override playbooks if they conflict.

### Quick ways to improve an answer

Ask follow-ups such as:

- `Show the exact source-backed claim for that.`
- `Turn this into a customer-ready email.`
- `Make this a step-by-step implementation plan.`
- `Stay in Fabric / Power BI for this answer.`
- `What should I validate before committing to this architecture?`
"""
    else:
        readme_body = """
### What this assistant is for

Use it for Azure Databricks troubleshooting, architecture questions, customer prep, implementation plans, and documentation-backed explanations. It combines Databricks model serving, Vector Search, curated playbooks, attachments, session context, source browsing, and live Azure Databricks status awareness.

### Best ways to use it

- Start in **Auto** unless you know the shape of answer you need.
- Paste the exact error, stack trace, query, config snippet, or symptom timeline.
- Attach or paste screenshots when UI state matters.
- Ask for **commands to run**, **where to check in the UI**, and **how to validate the fix**.
- Use the source browser after an answer to inspect the files that influenced it.

### Answer modes

| Mode | Use when you want |
| --- | --- |
| Auto | The assistant to infer whether this is troubleshooting, design, learning, status, or implementation. |
| Customer Meeting Prep | A concise briefing, likely customer questions, risks, recommended talk track, and follow-ups. |
| Solution Architecture | Design tradeoffs, prerequisites, security/networking implications, and decision points. |
| Troubleshooting | Ranked causes, evidence to collect, isolation tests, fixes, and validation steps. |
| Learning | A teachable explanation with mental model, practical example, and common misconceptions. |
| Deep Explanation | More depth on internals, constraints, edge cases, and why the recommendation works. |
| Implementation / Step-by-step | Ordered build steps, commands, checks, and rollback/validation notes. |

### Auto triage behavior

Auto mode looks for signals like error text, screenshots, networking terms, SQL/performance symptoms, Unity Catalog/security language, status/outage wording, and follow-up phrasing. It then routes the answer toward the most useful shape instead of giving a generic summary.

### Status awareness

The sidebar status card refreshes from the Azure Databricks status page and uses Central time with daylight saving. If you ask about a specific region, the assistant should answer from the status page first and avoid inventing outages.

### Trust but verify

Good answers should cite or name their sources, separate facts from assumptions, and say when evidence is missing. If an answer feels too broad, ask: `show the exact checks`, `give me the command sequence`, or `what source supports that?`
"""

    with st.expander("README", expanded=False):
        st.markdown(readme_body)




def render_chat():
    product_mode = st.session_state.get("_ui_product_mode", st.session_state.get("product_route_label", "Auto"))
    answer_mode = st.session_state.get("_ui_answer_mode", "Auto")
    k = st.session_state.get("_ui_context_k", FINAL_CONTEXT_K)
    if ENABLE_FABRIC:
        st.markdown(
            """
            <div class="dbx-command-hero">
                <div class="dbx-command-inner">
                    <div>
                        <div class="dbx-kicker">Field AI Command Center</div>
                        <h1 class="dbx-command-title">Databricks + Fabric Expert Assistant</h1>
                        <div class="dbx-command-copy">
                            Source-backed guidance for Databricks, Fabric, and Power BI architecture, troubleshooting, and customer-ready field workflows.
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="dbx-command-hero">
                <div class="dbx-command-inner">
                    <div>
                        <div class="dbx-kicker">Field AI Command Center</div>
                        <h1 class="dbx-command-title">Databricks Expert Assistant</h1>
                        <div class="dbx-command-copy">
                            Source-backed Databricks troubleshooting, architecture, implementation, and customer-prep guidance.
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    render_paste_screenshot_helper()

    fabric_example_questions = [
        "Fabric / Power BI route, Solution Architecture mode: Compare Direct Lake, Import, and DirectQuery for a Power BI semantic model over lakehouse data. Include governance, cost, performance, freshness, and validation checks.",
        "Fabric / Power BI route, Troubleshooting mode: A Fabric pipeline failed overnight after a schema change. Give me the evidence to collect, likely causes, isolation tests, and recovery steps.",
        "Fabric / Power BI route, Learning mode: Explain OneLake shortcuts versus copying data into a lakehouse. Use a practical example and call out common misconceptions.",
        "Fabric / Power BI route, Implementation / Step-by-step mode: Walk me through creating a Fabric lakehouse ingestion pattern and validating the data is ready for Power BI reporting.",
    ]

    compare_example_questions = [
        "Compare / Better Together route, Solution Architecture mode: A customer has Databricks Unity Catalog tables and a large Power BI audience. Recommend when to use Databricks SQL, Fabric/OneLake, Direct Lake, Import, or DirectQuery.",
        "Compare / Better Together route, Competitive / Customer Positioning mode: Databricks is challenging Power BI semantic models in a renewal. Help me prepare the customer response, talk track, landmines, and proof points.",
        "Compare / Better Together route, Customer Meeting Prep mode: Prepare a briefing for a customer deciding between Databricks-only, Fabric-only, and better-together architecture for analytics modernization.",
    ]

    databricks_example_questions = [
        "Databricks route, Troubleshooting mode: My Azure Databricks cluster is stuck in pending. Give me ranked causes, exact UI/log checks, isolation tests, fixes, and validation steps.",
        "Databricks route, Implementation / Step-by-step mode: Walk me through setting up Unity Catalog from scratch, including metastore, catalog, schema, storage credential, external location, permissions, and validation.",
        "Databricks route, Solution Architecture mode: Design private ADLS Gen2 access for Databricks after public network access is disabled. Separate private endpoint/DNS, Access Connector/RBAC, and Unity Catalog external locations.",
        "Databricks route, Deep Explanation mode: Explain how Delta Lake OPTIMIZE, ZORDER/liquid clustering, VACUUM, and data skipping affect query performance and maintenance risk.",
    ]

    example_questions = (
        fabric_example_questions + compare_example_questions + databricks_example_questions
        if ENABLE_FABRIC
        else databricks_example_questions
    )

    selected_example_prompt = st.session_state.pop("pending_example_prompt", "")

    with st.expander("Example questions", expanded=False):
        st.selectbox(
            "Example question",
            [EXAMPLE_PLACEHOLDER] + example_questions,
            key="example_question_picker",
            on_change=queue_selected_example_question,
            help="Pick one and the app will ask it automatically.",
        )

    render_readme_panel()

    last_user_question_for_report = ""
    for msg_index, msg in enumerate(st.session_state["messages"]):
        if msg["role"] == "user":
            last_user_question_for_report = msg.get("raw_content") or msg.get("content", "")

        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            if msg["role"] == "assistant":
                render_evidence_summary(msg.get("sources", []))
                render_shareable_report_button(
                    question=msg.get("question") or last_user_question_for_report,
                    answer=msg.get("raw_content") or msg.get("content", ""),
                    sources=msg.get("sources", []),
                    topic=msg.get("topic", ""),
                    intent=msg.get("intent", ""),
                    answer_mode=msg.get("answer_mode", ""),
                    key_suffix=f"history_{msg_index}",
                )

            if msg["role"] == "assistant" and msg.get("sources"):
                unique_sources = []
                seen_urls = set()

                for sid, title, url in msg["sources"]:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    unique_sources.append((sid, title, url))

                with st.expander(f"📚 Sources ({len(unique_sources)})", expanded=False):
                    for sid, title, url in unique_sources:
                        if url.startswith("playbook://"):
                            label = "🧭 Playbook"
                            st.markdown(f"{sid} {label} {title}")
                        else:
                            label = "🧠 Internal TSG" if url.startswith("internal_wiki://") else "📘 Docs"
                            st.markdown(f"{sid} {label} [{title}]({url})")

    if CHAT_INPUT_FILE_SUPPORT:
        chat_placeholder = "Ask a Databricks or Fabric question, paste error text, press Ctrl+V for screenshot, or attach a file..." if ENABLE_FABRIC else "Ask a Databricks question, paste error text, press Ctrl+V for screenshot, or attach a file..."
        chat_value = st.chat_input(
            chat_placeholder,
            accept_file="multiple",
            file_type=["png", "jpg", "jpeg", "txt", "log", "json", "sql", "py", "yml", "yaml", "md", "csv"],
        )

        prompt, uploaded_files = normalize_chat_input(chat_value)
    else:
        chat_placeholder = "Ask a Databricks or Fabric question, paste error text, press Ctrl+V for screenshot, or use the sidebar to attach a file..." if ENABLE_FABRIC else "Ask a Databricks question, paste error text, press Ctrl+V for screenshot, or use the sidebar to attach a file..."
        prompt = st.chat_input(chat_placeholder)
        uploaded_files = []

        if session_module.sidebar_uploaded_file:
            uploaded_files = session_module.sidebar_uploaded_file if isinstance(session_module.sidebar_uploaded_file, list) else [session_module.sidebar_uploaded_file]

    if selected_example_prompt and not prompt:
        prompt = selected_example_prompt

    if prompt or uploaded_files:
        st.session_state["pending_answer_mode_regeneration"] = False

        attachment_context = ""
        prompt_for_model = prompt.strip()

        if uploaded_files:
            attachment_parts = []

            with st.spinner("Reading attachments and extracting useful context..."):
                for uploaded_file in uploaded_files:
                    attachment_parts.append(extract_text_from_attachment(uploaded_file))

            attachment_context = "\n\n---\n\n".join(attachment_parts)

        if not prompt_for_model and attachment_context:
            prompt_for_model = "Help me troubleshoot the attached screenshot or file."

        user_display_content = prompt_for_model

        if attachment_context:
            file_count = len(uploaded_files)
            user_display_content += f"\n\n📎 {file_count} attachment{'s' if file_count != 1 else ''} included."

        logged_user_content = prompt_for_model
        if attachment_context:
            logged_user_content += f"\n\nAttachment context:\n{attachment_context}"

        st.session_state["messages"].append(
            {
                "role": "user",
                "content": user_display_content,
                "raw_content": logged_user_content,
            }
        )

        save_chat_message(
            session_id=st.session_state["session_id"],
            role="user",
            content=logged_user_content,
        )

        st.markdown('<div id="dbx-latest-exchange-start"></div>', unsafe_allow_html=True)

        with st.chat_message("user"):
            st.markdown(user_display_content)

            render_screenshot_triage_summary(attachment_context)

            if attachment_context:
                with st.expander("Attachment context used", expanded=False):
                    st.code(attachment_context)

        chat_history = get_recent_chat_history_before_current(max_messages=MAX_HISTORY_MESSAGES)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving sources, checking evidence, and drafting the answer..."):
                answer, sources, topic, intent = ask_databricks_sme(
                    prompt_for_model,
                    k=k,
                    answer_mode=answer_mode,
                    product_mode=product_mode,
                    chat_history=chat_history,
                    attachment_context=attachment_context,
                )

                answer_with_links = add_clickable_citations(answer, sources)

            st.markdown(answer_with_links)
            render_evidence_summary(sources)
            render_shareable_report_button(
                question=logged_user_content,
                answer=answer,
                sources=sources,
                topic=topic,
                intent=intent,
                answer_mode=answer_mode,
                key_suffix="live_answer",
            )

            if sources:
                unique_sources = []
                seen_urls = set()

                for sid, title, url in sources:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    unique_sources.append((sid, title, url))

                with st.expander(f"📚 Sources ({len(unique_sources)})", expanded=False):
                    for sid, title, url in unique_sources:
                        if url.startswith("playbook://"):
                            label = "🧭 Playbook"
                            st.markdown(f"{sid} {label} {title}")
                        else:
                            label = "🧠 Internal TSG" if url.startswith("internal_wiki://") else "📘 Docs"
                            st.markdown(f"{sid} {label} [{title}]({url})")

        render_scroll_to_latest_exchange_script()

        st.session_state["messages"].append(
            {
                "role": "assistant",
                "content": answer_with_links,
                "raw_content": answer,
                "question": logged_user_content,
                "sources": sources,
                "topic": topic,
                "intent": intent,
                "answer_mode": answer_mode,
            }
        )

        save_chat_message(
            session_id=st.session_state["session_id"],
            role="assistant",
            content=answer,
            topic=topic,
            intent=intent,
            sources=sources,
        )
        save_chat_to_local_storage(
            st.session_state["messages"],
            st.session_state.get("session_id", ""),
        )

        st.session_state["last_question"] = logged_user_content
        st.session_state["last_answer"] = answer
        st.session_state["last_sources"] = sources
        st.session_state["last_topic"] = topic
        st.session_state["last_intent"] = intent
        st.session_state["last_answer_mode"] = answer_mode
        st.session_state["last_prompt_for_model"] = prompt_for_model
        st.session_state["last_attachment_context"] = attachment_context
        st.session_state["last_chat_history"] = chat_history
        st.session_state["last_product_route"] = resolve_product_route(
            prompt_for_model,
            attachment_context,
            product_mode,
            chat_history,
        )
        st.session_state["last_answer_with_links"] = answer_with_links
        st.session_state["show_feedback_details"] = False
        st.session_state["pending_answer_mode_regeneration"] = False

    elif regenerate_last_answer(k=k, answer_mode=answer_mode, product_mode=product_mode):
        st.rerun()



def render_feedback_widget():
    if "last_answer" in st.session_state and FEEDBACK_LOGGING_ENABLED:
        st.divider()
        st.markdown("### Feedback on most recent answer")
        st.caption(
            f"Detected topic: `{st.session_state['last_topic']}` | "
            f"Detected intent: `{st.session_state['last_intent']}` | "
            f"Answer mode: `{st.session_state.get('last_answer_mode', 'Auto')}`"
        )

        render_feedback_controls("latest")

        with st.expander(
            "Add detailed feedback / correction",
            expanded=st.session_state.get("show_feedback_details", False),
        ):
            rating = st.radio(
                "Was this answer helpful?",
                ["👍 Good", "👎 Bad"],
                horizontal=True,
                key="feedback_rating",
            )

            correction = st.text_area(
                "What should the answer have said, or what was missing?",
                height=100,
                key="feedback_correction",
            )

            if st.button("Submit detailed feedback", key="submit_feedback"):
                try:
                    save_feedback(
                        question=st.session_state["last_question"],
                        answer=st.session_state["last_answer"],
                        topic=st.session_state["last_topic"],
                        intent=st.session_state["last_intent"],
                        rating=rating,
                        correction=correction,
                        sources=st.session_state["last_sources"],
                    )
                    st.success("Feedback saved.")
                except Exception as e:
                    st.error(f"Feedback could not be saved: {e}")
