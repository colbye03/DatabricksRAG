import html
import re

import streamlit as st


def add_clickable_citations(answer: str, sources):
    source_map = {sid: url for sid, title, url in sources}

    def repl(match):
        sid = match.group(0)
        url = source_map.get(sid)
        if url and not url.startswith("playbook://"):
            return f"[{sid}]({url})"
        return sid

    return re.sub(r"\[\d+\]", repl, answer)


def render_screenshot_triage_summary(attachment_context: str):
    from app.retrieval import screenshot_triage_metadata

    triage = screenshot_triage_metadata(attachment_context)

    if not triage:
        return

    with st.expander("Screenshot auto-triage", expanded=True):
        cols = st.columns(3)
        cols[0].metric("Product area", triage.get("product_area") or "Unknown")
        cols[1].metric("Severity", triage.get("severity") or "Unknown")
        cols[2].metric("Confidence", triage.get("confidence") or "Unknown")
        st.markdown(f"**Detected symptom:** {triage.get('detected_symptom') or 'Unknown'}")
        st.markdown(f"**Likely topic:** `{triage.get('likely_topic') or 'general'}`")

        if triage.get("ui_area"):
            st.markdown(f"**UI area:** {triage['ui_area']}")
        if triage.get("error_codes") and triage["error_codes"] != "None detected":
            st.markdown(f"**Error codes / text:** {triage['error_codes']}")
        if triage.get("suggested_first_checks") and triage["suggested_first_checks"] != "None provided":
            st.markdown(f"**First checks:** {triage['suggested_first_checks']}")


def render_evidence_summary(sources):
    from app.feedback import evidence_summary_for_sources

    summary = evidence_summary_for_sources(sources)
    st.markdown(
        f"""
        <div class="evidence-strip {summary['class']}">
          <strong>Evidence quality: {summary['level']}.</strong>
          {summary['note']} Sources: {summary['official']} docs, {summary['internal']} internal, {summary['playbook']} playbook.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_source_card(source_id: str, title: str, url: str):
    url = url or ""
    source_kind = "Curated playbook" if url.startswith("playbook://") else "Internal TSG" if url.startswith("internal_wiki://") else "Docs / indexed source"
    safe_title = html.escape(title or "Untitled source")
    st.markdown(
        f"""
        <div class="source-card">
          <div class="source-title">{html.escape(source_id)} {safe_title}</div>
          <div class="source-meta">{html.escape(source_kind)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_source_list_expander(sources, title_prefix: str = "📚 Sources"):
    unique_sources = []
    seen_urls = set()

    for sid, title, url in sources or []:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unique_sources.append((sid, title, url))

    with st.expander(f"{title_prefix} ({len(unique_sources)})", expanded=False):
        for sid, title, url in unique_sources:
            if (url or "").startswith("playbook://"):
                st.markdown(f"{sid} 🧭 Playbook {title}")
            else:
                label = "🧠 Internal TSG" if (url or "").startswith("internal_wiki://") else "📘 Docs"
                st.markdown(f"{sid} {label} [{title}]({url})")
