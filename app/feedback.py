import html
import os
import re
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from app.clients import workspace_client
from app.config import CHAT_SESSIONS_TABLE, ENABLE_FABRIC, FEEDBACK_LOGGING_ENABLED, FEEDBACK_TABLE, LOG_CHAT_TRANSCRIPT, STATUS_DISPLAY_TIMEZONE_NAME
from app.retrieval import sql_escape
from app.ui.components import render_source_card

def save_feedback(question, answer, topic, intent, rating, correction, sources):
    if workspace_client is None:
        raise ValueError("Databricks workspace client is not configured.")

    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise ValueError("Missing DATABRICKS_WAREHOUSE_ID environment variable.")

    feedback_id = str(uuid.uuid4())
    sources_text = "\n".join([f"{sid} {title} {url}" for sid, title, url in sources])

    sql = f"""
    INSERT INTO {FEEDBACK_TABLE}
    VALUES (
      '{feedback_id}',
      '{sql_escape(question)}',
      '{sql_escape(answer)}',
      '{sql_escape(topic)}',
      '{sql_escape(intent)}',
      '{sql_escape(rating)}',
      '{sql_escape(correction)}',
      '{sql_escape(sources_text)}',
      current_timestamp()
    )
    """

    workspace_client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
    )

    return feedback_id


def save_chat_message(session_id, role, content, topic="", intent="", sources=None):
    if not LOG_CHAT_TRANSCRIPT:
        return

    if workspace_client is None:
        return

    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        return

    message_id = str(uuid.uuid4())
    sources = sources or []
    sources_text = "\n".join([f"{sid} {title} {url}" for sid, title, url in sources])

    sql = f"""
    INSERT INTO {CHAT_SESSIONS_TABLE}
    VALUES (
      '{sql_escape(session_id)}',
      '{message_id}',
      '{sql_escape(role)}',
      '{sql_escape(content)}',
      '{sql_escape(topic)}',
      '{sql_escape(intent)}',
      '{sql_escape(sources_text)}',
      current_timestamp()
    )
    """

    try:
        workspace_client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=sql,
        )
    except Exception:
        pass


def render_feedback_controls(location: str):
    if "last_answer" not in st.session_state or not FEEDBACK_LOGGING_ENABLED:
        return

    c1, c2, c3 = st.columns([0.08, 0.08, 0.84])

    with c1:
        if st.button("👍", key=f"good_{location}", help="Mark last answer as good"):
            try:
                save_feedback(
                    question=st.session_state["last_question"],
                    answer=st.session_state["last_answer"],
                    topic=st.session_state["last_topic"],
                    intent=st.session_state["last_intent"],
                    rating="👍 Good",
                    correction="",
                    sources=st.session_state["last_sources"],
                )
                st.toast("Feedback saved")
            except Exception as e:
                st.error(f"Feedback could not be saved: {e}")

    with c2:
        if st.button("👎", key=f"bad_{location}", help="Mark last answer as bad"):
            st.session_state["show_feedback_details"] = True


def evidence_summary_for_sources(sources):
    sources = sources or []
    unique_urls = set()
    counts = {"official": 0, "internal": 0, "playbook": 0}

    for _, _, url in sources:
        url = url or ""
        if url in unique_urls:
            continue
        unique_urls.add(url)

        if url.startswith("playbook://"):
            counts["playbook"] += 1
        elif url.startswith("internal_wiki://"):
            counts["internal"] += 1
        elif url:
            counts["official"] += 1

    cited_count = sum(counts.values())
    documentary_count = counts["official"] + counts["internal"]

    if documentary_count >= 2:
        level = "Strong"
        css_class = "strong"
        note = "Multiple indexed sources are available for this answer."
    elif documentary_count == 1 or counts["playbook"] >= 1:
        level = "Mixed"
        css_class = "mixed"
        note = "Useful source coverage, but verify details before customer commitment."
    else:
        level = "Thin"
        css_class = "thin"
        note = "Limited retrieved evidence; treat the answer as guidance to validate."

    return {
        "level": level,
        "class": css_class,
        "note": note,
        "official": counts["official"],
        "internal": counts["internal"],
        "playbook": counts["playbook"],
        "total": cited_count,
    }



def report_file_slug(text: str, max_chars: int = 52) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "report").strip().lower()).strip("-")
        if not slug:
                slug = "report"
        return slug[:max_chars].strip("-") or "report"


def source_rows_for_report(sources):
        rows = []
        seen = set()

        for sid, title, url in sources or []:
                key = url or title or sid
                if key in seen:
                        continue
                seen.add(key)

                url = url or ""
                if url.startswith("playbook://"):
                        source_kind = "Curated playbook"
                elif url.startswith("internal_wiki://"):
                        source_kind = "Internal TSG"
                else:
                        source_kind = "Docs / indexed source"

                rows.append(
                        {
                                "sid": sid or "",
                                "title": title or "Untitled source",
                                "url": url,
                                "kind": source_kind,
                        }
                )

        return rows


def build_shareable_report_html(question: str, answer: str, sources, topic: str = "", intent: str = "", answer_mode: str = "") -> str:
    try:
        generated_at = datetime.now(ZoneInfo(STATUS_DISPLAY_TIMEZONE_NAME)).strftime("%Y-%m-%d %I:%M %p %Z")
    except Exception:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %I:%M %p UTC")

    summary = evidence_summary_for_sources(sources)
    source_rows = source_rows_for_report(sources)
    app_title = "Databricks + Fabric Expert Assistant" if ENABLE_FABRIC else "Databricks Expert Assistant"

    source_items = []
    for source in source_rows:
        title = html.escape(source["title"])
        sid = html.escape(source["sid"])
        kind = html.escape(source["kind"])
        url = source["url"]

        if url and not url.startswith("playbook://"):
            safe_url = html.escape(url, quote=True)
            source_line = f'<a href="{safe_url}">{title}</a>'
        else:
            source_line = title

        source_items.append(
            f"""
            <li>
                <div class="source-title">{sid} {source_line}</div>
                <div class="source-kind">{kind}</div>
            </li>
            """
        )

    sources_html = "\n".join(source_items) if source_items else "<li>No retrieved sources were attached to this answer.</li>"
    escaped_question = html.escape(question or "Question not captured for this report.")
    escaped_answer = html.escape(answer or "")
    escaped_topic = html.escape(topic or "not detected")
    escaped_intent = html.escape(intent or "not detected")
    escaped_mode = html.escape(answer_mode or "Auto")

    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(app_title)} Report</title>
    <style>
        body {{
            margin: 0;
            background: #f6f8fb;
            color: #111827;
            font-family: "Segoe UI", Arial, sans-serif;
            line-height: 1.55;
        }}
        .page {{
            max-width: 920px;
            margin: 0 auto;
            padding: 32px 22px 48px;
        }}
        .header {{
            border-radius: 8px;
            background: #0b1220;
            color: #f8fafc;
            padding: 22px 24px;
            border-bottom: 5px solid #2563eb;
        }}
        .kicker {{
            color: #9bd7ff;
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
        }}
        h1 {{ margin: 4px 0 8px; font-size: 28px; line-height: 1.2; }}
        h2 {{ margin: 26px 0 10px; font-size: 18px; }}
        .meta {{ color: #d9e5f2; font-size: 13px; }}
        .box {{
            background: #ffffff;
            border: 1px solid #d7dde8;
            border-radius: 8px;
            padding: 16px 18px;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.05);
        }}
        .answer {{ white-space: pre-wrap; }}
        .evidence {{
            margin-top: 14px;
            border-left: 5px solid #2563eb;
            background: #eff6ff;
            color: #1e3a8a;
        }}
        ul.sources {{ padding-left: 22px; }}
        ul.sources li {{ margin-bottom: 12px; }}
        .source-title {{ font-weight: 700; }}
        .source-kind {{ color: #5b677a; font-size: 13px; }}
        a {{ color: #1d4ed8; }}
        .footer {{ margin-top: 28px; color: #5b677a; font-size: 12px; }}
    </style>
</head>
<body>
    <main class="page">
        <section class="header">
            <div class="kicker">Shareable field report</div>
            <h1>{html.escape(app_title)}</h1>
            <div class="meta">Generated {html.escape(generated_at)} | Mode: {escaped_mode} | Topic: {escaped_topic} | Intent: {escaped_intent}</div>
        </section>

        <section>
            <h2>Question</h2>
            <div class="box">{escaped_question}</div>
        </section>

        <section>
            <h2>Answer</h2>
            <div class="box answer">{escaped_answer}</div>
        </section>

        <section>
            <h2>Evidence</h2>
            <div class="box evidence"><strong>Evidence quality: {html.escape(summary['level'])}.</strong> {html.escape(summary['note'])} Sources: {summary['official']} docs, {summary['internal']} internal, {summary['playbook']} playbook.</div>
            <ul class="sources">{sources_html}</ul>
        </section>

        <section class="footer">
            Generated from {html.escape(app_title)}. Review customer-facing language and source coverage before forwarding externally.
        </section>
    </main>
</body>
</html>"""


def render_shareable_report_button(question: str, answer: str, sources, topic: str = "", intent: str = "", answer_mode: str = "", key_suffix: str = "latest"):
    if not answer:
        return

    report_html = build_shareable_report_html(
        question=question,
        answer=answer,
        sources=sources,
        topic=topic,
        intent=intent,
        answer_mode=answer_mode,
    )
    timestamp = datetime.now(ZoneInfo(STATUS_DISPLAY_TIMEZONE_NAME)).strftime("%Y%m%d-%H%M")
    file_name = f"expert-assistant-report-{timestamp}-{report_file_slug(question)}.html"

    st.download_button(
        "Download shareable report",
        data=report_html.encode("utf-8"),
        file_name=file_name,
        mime="text/html",
        key=f"share_report_{key_suffix}",
        help="Download a clean HTML report with the question, answer, evidence summary, and source links.",
    )


def render_left_source_pane():
    """Show the source files for the most recent answer in the left pane."""
    sources = st.session_state.get("last_sources", []) or []

    st.divider()
    st.subheader("Answer sources")

    if not sources:
        st.caption("Ask a question to populate source files here.")
        return

    summary = evidence_summary_for_sources(sources)
    st.caption(
        f"Evidence: {summary['level']} | "
        f"Docs {summary['official']} | Internal {summary['internal']} | Playbooks {summary['playbook']}"
    )

    unique_sources = []
    seen = set()

    for sid, title, url in sources:
        key = url or title or sid
        if key in seen:
            continue
        seen.add(key)
        unique_sources.append((sid, title, url))

    with st.expander(f"Source files for last answer ({len(unique_sources)})", expanded=False):
        for sid, title, url in unique_sources:
            url = url or ""
            source_kind = "Curated playbook" if url.startswith("playbook://") else "Internal TSG" if url.startswith("internal_wiki://") else "Docs / indexed source"
            safe_title = title or "Untitled source"

            render_source_card(sid, safe_title, url)

            if url and not url.startswith("playbook://"):
                st.markdown(f"[Open source]({url})")
            elif url.startswith("playbook://"):
                st.caption("Built-in expert playbook used as internal guidance.")

