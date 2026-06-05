import html
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from app.clients import CLIENT_INIT_ERROR, deploy_client, fabric_vs_index, powerbi_vs_index, vs_index
from app.config import *
from app.feedback import save_chat_message
from app.formats import FORMAT_BY_INTENT
from app.prompts import SYSTEM_PROMPT
from app.retrieval import (
    attachment_has_real_text,
    build_context,
    build_retrieval_question,
    choose_chat_model,
    hybrid_retrieve,
    predict_chat_text,
    repair_answer_if_needed,
    sanitize_csp_customer_email,
    screenshot_triage_metadata,
)
from app.routing import (
    build_customer_written_output_instruction,
    build_followup_instruction,
    build_quality_instruction,
    build_topic_instruction,
    is_cli_request,
    is_compare_request,
    resolve_product_route,
    user_says_prereq_done,
)
from app.topics import TOPIC_CONFIG
from app.ui.components import add_clickable_citations

DATABRICKS_STATUS_SUMMARY_URL = os.environ.get(
    "DATABRICKS_STATUS_SUMMARY_URL",
    "https://status.azuredatabricks.net/",
)


def is_status_page_question(question: str) -> bool:
    q = (question or "").lower()
    status_terms = [
        "outage", "outages", "incident", "incidents", "status page",
        "status.databricks", "service status", "platform status",
        "current status", "status for", "status in", "any issues",
        "databricks down", "is databricks down", "is dbx down",
        "system down", "service degradation", "degraded", "availability",
    ]
    return any(term in q for term in status_terms)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_databricks_status_page():
    request = urllib.request.Request(
        DATABRICKS_STATUS_SUMMARY_URL,
        headers={"User-Agent": "databricks-sme-agent/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read().decode("utf-8", errors="replace")
        return payload, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, str(exc)


def visible_status_text(page_html: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", " ", page_html or "")
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def detect_overall_status(status_text: str) -> str:
    known_statuses = [
        "All Services Operational",
        "Partial System Outage",
        "Major Service Outage",
        "Minor Service Outage",
        "Degraded Performance",
        "Service Under Maintenance",
    ]
    for status in known_statuses:
        if status.lower() in status_text.lower():
            return status
    return "Unknown from visible page text"


def clean_status_value(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def extract_region_statuses(page_html: str):
    region_statuses = []
    pattern = re.compile(
        r'<p[^>]*class="[^"]*container_name[^"]*"[^>]*>(.*?)</p>.*?'
        r'<p[^>]*class="[^"]*pull-right[^"]*"[^>]*>(.*?)</p>',
        re.IGNORECASE | re.DOTALL,
    )

    for region, status in pattern.findall(page_html or ""):
        region = clean_status_value(re.sub(r"(?s)<[^>]+>", " ", region))
        status = clean_status_value(re.sub(r"(?s)<[^>]+>", " ", status))
        if region and status and region.lower() != "name":
            region_statuses.append((region, status))

    return region_statuses


def normalize_region_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def requested_region_status(question: str, region_statuses):
    q_norm = normalize_region_name(question)
    for region, status in region_statuses:
        if normalize_region_name(region) in q_norm:
            return region, status
    return "", ""


def non_operational_regions(region_statuses):
    return [
        (region, status)
        for region, status in region_statuses
        if "operational" not in status.lower()
    ]


def query_param_value(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
    except Exception:
        value = default
    if isinstance(value, list):
        value = value[0] if value else default
    return str(value or default).strip()


def preview_impacted_regions():
    if not STATUS_PREVIEW_ENABLED:
        return []
    preview_mode = query_param_value("status_preview").lower()
    if preview_mode not in {"region-down", "service-down", "outage"}:
        return []
    region = query_param_value("status_region", STATUS_PREVIEW_REGION)
    service = query_param_value("status_service", STATUS_PREVIEW_SERVICE)
    state = query_param_value("status_state", "Service disruption")
    label = f"{region} - {service}" if service else region
    return [(label, state)]


def second_sunday_in_march_utc(year: int) -> datetime:
    march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
    days_until_sunday = (6 - march_first.weekday()) % 7
    second_sunday_day = 1 + days_until_sunday + 7
    return datetime(year, 3, second_sunday_day, 8, 0, tzinfo=timezone.utc)


def first_sunday_in_november_utc(year: int) -> datetime:
    november_first = datetime(year, 11, 1, tzinfo=timezone.utc)
    days_until_sunday = (6 - november_first.weekday()) % 7
    first_sunday_day = 1 + days_until_sunday
    return datetime(year, 11, first_sunday_day, 7, 0, tzinfo=timezone.utc)


def central_time_label() -> str:
    try:
        return datetime.now(ZoneInfo(STATUS_DISPLAY_TIMEZONE_NAME)).strftime("%H:%M:%S %Z")
    except Exception:
        now_utc = datetime.now(timezone.utc)
        dst_start = second_sunday_in_march_utc(now_utc.year)
        dst_end = first_sunday_in_november_utc(now_utc.year)
        if dst_start <= now_utc < dst_end:
            return (now_utc + timedelta(hours=-5)).strftime("%H:%M:%S CDT")
        return (now_utc + timedelta(hours=-6)).strftime("%H:%M:%S CST")


def render_azure_databricks_status_banner():
    page_html, error = fetch_databricks_status_page()
    checked_at = central_time_label()
    if not page_html:
        st.markdown(
            f"""
            <div class="dbx-status-banner neutral">
                <div class="dbx-status-heading">
                    <span>Azure Databricks regional health unavailable</span>
                    <span class="dbx-status-pill">Status check</span>
                </div>
                <div class="dbx-status-subtext">Could not refresh the Azure Databricks status page. Last checked {checked_at}.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    status_text = visible_status_text(page_html)
    overall_status = detect_overall_status(status_text)
    region_statuses = extract_region_statuses(page_html)
    impacted = preview_impacted_regions() or non_operational_regions(region_statuses)

    if impacted:
        issue_rows = "".join(
            "<div class=\"dbx-status-issue-row\">"
            f"<span class=\"dbx-status-issue-name\">{html.escape(region)}</span>"
            f"<span class=\"dbx-status-issue-state\">{html.escape(status)}</span>"
            "</div>"
            for region, status in impacted[:8]
        )
        hidden_count = len(impacted) - 8
        more_text = f"<div class=\"dbx-status-subtext\">Plus {hidden_count} more impacted area(s).</div>" if hidden_count > 0 else ""
        st.markdown(
            f"""
            <div class="dbx-status-banner issue">
                <div class="dbx-status-heading">
                    <span>Azure Databricks reported issues detected</span>
                    <span class="dbx-status-pill">{len(impacted)} impacted</span>
                </div>
                <div class="dbx-status-subtext">Affected regions or service areas. Updated {checked_at}.</div>
                <div class="dbx-status-issue-list">{issue_rows}</div>
                {more_text}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        detail_text = f"No regional issues detected. Updated {checked_at}."
        if overall_status and not overall_status.lower().startswith("unknown"):
            detail_text = f"No regional issues detected. {overall_status}. Updated {checked_at}."
        st.markdown(
            f"""
            <div class="dbx-status-banner">
                <div class="dbx-status-heading">
                    <span>Azure Databricks regions show healthy</span>
                    <span class="dbx-status-pill">Healthy</span>
                </div>
                <div class="dbx-status-subtext">{html.escape(detail_text)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_sidebar_status_card():
    render_azure_databricks_status_banner()


if hasattr(st, "fragment"):
    render_sidebar_status_card = st.fragment(run_every="60s")(render_sidebar_status_card)


def build_databricks_status_context(question: str) -> str:
    if not is_status_page_question(question):
        return ""

    page_html, error = fetch_databricks_status_page()
    if not page_html:
        return (
            "DATABRICKS STATUS PAGE CHECK\n"
            f"Source: {DATABRICKS_STATUS_SUMMARY_URL}\n"
            "Result: Status page check could not be completed.\n"
            f"Detail: {error or 'Unknown error'}\n"
            "Instruction: Be transparent that live status could not be checked, then continue with normal troubleshooting guidance.\n"
        )

    status_text = visible_status_text(page_html)
    overall_status = detect_overall_status(status_text)
    region_statuses = extract_region_statuses(page_html)
    requested_region, requested_status = requested_region_status(question, region_statuses)
    impacted_regions = non_operational_regions(region_statuses)
    important_lines = []
    for line in status_text.splitlines():
        line_lower = line.lower()
        if any(term in line_lower for term in [
            "all services operational", "outage", "incident", "degraded",
            "maintenance", "updated", "azure databricks", "status by azure region",
        ]):
            if line not in important_lines:
                important_lines.append(line)

    excerpt = "\n".join(important_lines[:20]) or status_text[:1200]

    lines = [
        "DATABRICKS STATUS PAGE CHECK",
        f"Source: {DATABRICKS_STATUS_SUMMARY_URL}",
        "Page: Azure Databricks status",
        f"Overall status: {overall_status}",
        f"Requested region: {requested_region or 'Not specified or not found'}",
        f"Requested region status: {requested_status or 'Not available from parsed page text'}",
        f"Impacted regions count: {len(impacted_regions)}",
        "Impacted regions: " + (", ".join([f"{region}: {status}" for region, status in impacted_regions[:12]]) if impacted_regions else "None detected"),
        "",
        "Relevant page text:",
        excerpt,
        "",
        "Instruction: Start outage-related answers with a direct answer. If a requested region status is available, say '<Region> is currently <Status> according to the Azure Databricks status page.' Do not tell the user to navigate to the page as the main answer. If no incidents are visible, say the Azure Databricks status page does not show an active platform-wide issue and then troubleshoot workspace, region, network, auth, compute, SQL warehouse, job, or configuration causes.",
    ]
    return "\n".join(lines)


def ask_databricks_sme(
    question: str,
    k: int = FINAL_CONTEXT_K,
    answer_mode: str = "Auto",
    product_mode: str = "Auto",
    chat_history: str = "",
    attachment_context: str = "",
):
    selected_product = resolve_product_route(question, attachment_context, product_mode, chat_history)
    if selected_product == "fabric":
        selected_index = fabric_vs_index or powerbi_vs_index
    elif selected_product == "powerbi":
        selected_index = powerbi_vs_index
    else:
        selected_index = vs_index
    if selected_product == "compare":
        selected_index = vs_index or fabric_vs_index or powerbi_vs_index

    if deploy_client is None or selected_index is None:
        return (
            "The assistant is running, but it is not connected to Databricks yet.\n\n"
            "Configure the web app settings for `DATABRICKS_HOST` plus either "
            "`DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET` or `DATABRICKS_TOKEN`, then restart the web app.\n\n"
            f"Current startup detail: {CLIENT_INIT_ERROR or 'Databricks client not initialized.'}\n\n"
            f"Selected product route: `{selected_product}`.",
            [],
            "appservice_configuration",
            "configuration",
        )

    if attachment_context and not attachment_has_real_text(attachment_context):
        if (
            "SCREENSHOT_MODEL" in attachment_context
            or "OCR endpoint" in attachment_context
            or "serving-endpoints" in attachment_context
            or "ENDPOINT_NOT_FOUND" in attachment_context
        ):
            return (
                "I could not troubleshoot the screenshot because screenshot OCR is not configured correctly.\n\n"
                "This is an app configuration issue, not the Databricks workload error in the screenshot.\n\n"
                "Next step: paste the visible screenshot error text directly into the chat, or configure "
                "`SCREENSHOT_MODEL` to a real multimodal Databricks serving endpoint.",
                [],
                "attachment_processing",
                "troubleshooting",
            )

        return (
            "I could not read usable text from the attachment. Paste the visible error message, error code, "
            "and where it appears. I should not guess from the screenshot.",
            [],
            "attachment_processing",
            "troubleshooting",
        )

    status_context = build_databricks_status_context(question)

    retrieval_question = build_retrieval_question(
        question=question,
        chat_history=chat_history,
        attachment_context=attachment_context,
        product=selected_product,
    )

    topic, intent, rows = hybrid_retrieve(retrieval_question, k=k, product=selected_product)
    q_lower = question.lower()
    triage = screenshot_triage_metadata(attachment_context)

    if triage and answer_mode == "Auto":
        triage_topic = (triage.get("likely_topic") or "").strip()
        triage_intent = (triage.get("likely_intent") or "").strip()

        if triage_topic in TOPIC_CONFIG:
            topic = triage_topic
        elif triage_topic in ["model_serving", "sql_warehouse", "lakeflow"]:
            topic = triage_topic

        if triage_intent in FORMAT_BY_INTENT:
            intent = triage_intent
        elif triage_topic and triage_topic != "general":
            intent = "deep_troubleshooting"

    # Auto escalation by topic.
    if topic == "fabric_mirroring" and intent not in ["commands"]:
        intent = "deep_integration"

    if topic == "adls_private_access" and intent not in ["commands"]:
        if any(x in q_lower for x in [
            "error", "cannot", "can't", "cant", "failed", "not working",
            "resolve", "troubleshoot", "how do i resolve", "why",
            "subnet has a delegation", "public network access disabled",
            "private access only", "private network only",
        ]):
            intent = "deep_troubleshooting"
        else:
            intent = "deep_implementation"

    if topic == "cluster_bootstrap" and intent not in ["commands"]:
        intent = "deep_troubleshooting"

    if topic == "spark_performance" and intent not in ["commands", "meeting_prep"]:
        intent = "deep_troubleshooting"

    if topic == "compliance_architecture" and intent not in ["commands"]:
        intent = "deep_architecture"

    if topic == "unity_catalog_setup" and intent in ["explanation", "implementation"]:
        intent = "deep_implementation"

    # Auto escalation by phrasing.
    if intent in ["explanation", "learning", "deep_explanation"] and any(x in q_lower for x in [
        "full super accurate", "super accurate", "break down", "one by one",
        "each question", "official documents", "downstream impact",
    ]):
        intent = "deep_explanation"

    if intent in ["explanation", "learning"] and any(x in q_lower for x in [
        "hand holding", "dont miss anything", "don't miss anything",
        "from scratch", "start from the beginning", "end to end", "end-to-end",
    ]):
        intent = "deep_implementation"

    # Manual answer mode overrides.
    if answer_mode == "Customer Meeting Prep":
        intent = "meeting_prep"
    elif answer_mode == "Competitive / Customer Positioning":
        intent = "competitive_positioning"
    elif answer_mode == "Solution Architecture":
        if topic in ["compliance_architecture", "architecture"]:
            intent = "deep_architecture"
        else:
            intent = "architecture"
    elif answer_mode == "Troubleshooting Runbook":
        intent = "deep_troubleshooting"
    elif answer_mode == "Learning":
        intent = "learning"
    elif answer_mode == "Deep Explanation":
        intent = "deep_explanation"
    elif answer_mode == "Implementation / Step-by-step":
        if topic == "fabric_mirroring":
            intent = "deep_integration"
        else:
            intent = "deep_implementation"
    elif answer_mode == "Comparison":
        intent = "comparison"

    if attachment_has_real_text(attachment_context) and answer_mode == "Auto" and intent not in [
        "commands", "deep_implementation", "deep_architecture", "deep_integration"
    ]:
        intent = "deep_troubleshooting" if triage else "troubleshooting"

    context, sources = build_context(rows)
    if status_context:
        context = f"{status_context}\n\n{context}" if context else status_context
        sources = [("status", "Databricks status page", DATABRICKS_STATUS_SUMMARY_URL)] + sources

    if not rows and not status_context:
        return (
            f"I could not retrieve enough relevant {selected_product.title()} documentation context to answer confidently. "
            "Include the exact error message, product area, and failing step.",
            sources,
            topic,
            intent,
        )

    answer_format = FORMAT_BY_INTENT.get(intent, FORMAT_BY_INTENT["explanation"])
    if selected_product == "compare" and intent in ["explanation", "comparison", "meeting_prep"]:
        intent = "competitive_positioning" if is_compare_request(f"{question}\n{chat_history}") else "comparison"
        answer_format = FORMAT_BY_INTENT.get(intent, FORMAT_BY_INTENT["comparison"])

    if topic == "fabric_mirroring":
        answer_format = (
            "MANDATORY FABRIC MIRRORING IMPLEMENTATION STRUCTURE. Use these exact section headings:\n"
            "1. First decision / supported path\n"
            "   - State whether the retrieved evidence supports Fabric mirrored database/mirroring, OneLake shortcut/read access to UC data, or both.\n"
            "   - If the evidence is shortcut/read-access docs, do NOT call it replicated mirroring. Say it is the supported Fabric read-access pattern and that true mirrored database availability must be confirmed in Fabric.\n"
            "2. Assumptions and target outcome\n"
            "3. Prerequisites and blockers\n"
            "4. Identity and permissions\n"
            "5. Fabric-side setup steps\n"
            "6. Databricks / Unity Catalog validation steps\n"
            "7. Supported and unsupported objects\n"
            "8. Security, lineage, and governance caveats\n"
            "9. Go-live validation checklist\n"
            "10. Troubleshooting if it fails\n"
            "11. Fallback options\n"
            "12. Next best action\n"
        )
    elif topic == "powerbi_semantic_architecture":
        answer_format = (
            "MANDATORY POWER BI / FABRIC SEMANTIC ARCHITECTURE STRUCTURE. Use these exact section headings:\n"
            "1. Direct Recommendation\n"
            "2. Pattern Decision Matrix\n"
            "3. Recommended Reference Architecture\n"
            "4. Governance And Security Boundary\n"
            "5. Performance, Freshness, And Cost Tradeoffs\n"
            "6. Databricks-Backed Data Patterns\n"
            "7. Proof-Of-Concept Validation Checklist\n"
            "8. Risks, Unknowns, And Questions To Confirm\n"
            "\n"
            "The decision matrix must compare Direct Lake, Import, DirectQuery, and Composite/Hybrid when relevant across: use when, avoid when, data movement/caching, freshness, performance, governance/security, and cost/capacity.\n"
            "The direct recommendation must be conditional for Databricks Unity Catalog source data. Do not say the production recommendation is simply Direct Lake. Say Direct Lake is the preferred Fabric-native pattern only when the data is supported in Fabric/OneLake; otherwise choose DirectQuery to Databricks SQL or Import based on freshness, performance, and governance requirements.\n"
        )
    followup_instruction = build_followup_instruction(question, chat_history, intent)
    topic_instruction = build_topic_instruction(topic, question)
    quality_instruction = build_quality_instruction(intent, topic, answer_mode)
    customer_written_instruction = build_customer_written_output_instruction(question, topic)

    if topic == "fabric_mirroring" and user_says_prereq_done(question, "unity_catalog"):
        topic_instruction += (
            "USER CONTEXT OVERRIDE:\n"
            "- The user stated Databricks and Unity Catalog are already set up.\n"
            "- Do not include Unity Catalog metastore, workspace assignment, catalog creation, or schema creation setup steps.\n"
            "- Start from Fabric-side mirroring setup and Databricks-side permissions/connection validation only.\n\n"
        )

    source_coverage_warning = ""

    screenshot_triage_instruction = ""

    if triage:
        screenshot_triage_instruction = (
            "SCREENSHOT AUTO-TRIAGE INSTRUCTIONS:\n"
            f"- Product area detected: {triage.get('product_area') or 'Unknown'}\n"
            f"- UI area detected: {triage.get('ui_area') or 'Unknown'}\n"
            f"- Symptom detected: {triage.get('detected_symptom') or 'Unknown'}\n"
            f"- Severity: {triage.get('severity') or 'unknown'}; confidence: {triage.get('confidence') or 'unknown'}\n"
            f"- Missing info: {triage.get('missing_info') or 'None identified'}\n"
            "- Start the answer with a short 'Screenshot triage' section before the runbook.\n"
            "- Use only visible/extracted screenshot evidence. Do not invent hidden UI text, IDs, error codes, or customer details.\n"
            "- If confidence is low, say what is uncertain and ask for the minimum missing artifact.\n"
            "- Then provide the fastest safe troubleshooting path, ranked likely causes, exact UI/log checks, fixes by cause, validation, and what to collect if unresolved.\n\n"
        )

    if topic == "fabric_mirroring":
        has_fabric_source = any(
            "fabric" in (title or "").lower() or "fabric" in (url or "").lower()
            for _, title, url in sources
        )
        source_text = " ".join([f"{title} {url}" for _, title, url in sources]).lower()
        has_shortcut_source = any(term in source_text for term in [
            "shortcut", "onelake", "use microsoft fabric to read data", "partners/bi/fabric"
        ])
        has_mirrored_database_source = any(term in source_text for term in [
            "mirrored database", "mirroring", "mirror azure databricks"
        ])

        if not has_fabric_source:
            source_coverage_warning += (
                "FABRIC SOURCE WARNING:\n"
                "- Retrieved context does not appear to include enough Microsoft Fabric documentation.\n"
                "- Do not fabricate exact Fabric UI steps.\n"
                "- Provide a conceptual Fabric-owned setup flow and clearly state what must be confirmed in current Microsoft Fabric docs.\n\n"
            )
        elif has_shortcut_source and not has_mirrored_database_source:
            source_coverage_warning += (
                "FABRIC PATH WARNING:\n"
                "- Retrieved context appears to describe OneLake shortcut / Fabric read access to Unity Catalog data, not necessarily Fabric mirrored database replication.\n"
                "- Start the answer by saying this distinction clearly.\n"
                "- Do not say the data is replicated or mirrored if the source only supports shortcut/read-access semantics.\n\n"
            )

    if topic == "adls_private_access":
        source_text = " ".join([f"{title} {url}" for _, title, url in sources]).lower()
        expected = [
            "private endpoint",
            "privatelink",
            "dfs",
            "storage account",
            "unity catalog",
            "external location",
            "access connector",
        ]

        if not any(term in source_text for term in expected):
            source_coverage_warning += (
                "ADLS PRIVATE ACCESS SOURCE WARNING:\n"
                "- Retrieved context may not include enough storage private endpoint/private DNS documentation.\n"
                "- Do not confuse workspace private endpoints with storage private endpoints.\n"
                "- Provide a safe network + identity + Unity Catalog troubleshooting flow.\n\n"
            )

    if selected_product == "compare":
        source_text = " ".join([f"{title} {url}" for _, title, url in sources]).lower()
        has_databricks_source = "databricks" in source_text or "docs.databricks.com" in source_text
        has_fabric_source = "fabric" in source_text or "power bi" in source_text

        if not (has_databricks_source and has_fabric_source):
            source_coverage_warning += (
                "COMPARE SOURCE WARNING:\n"
                "- Retrieved context may be uneven across Databricks and Fabric/Power BI.\n"
                "- Be explicit about which product has evidence and which parts are field/architecture guidance.\n"
                "- Do not invent product limitations or roadmap commitments.\n\n"
            )

    if intent == "competitive_positioning":
        source_text = " ".join([f"{title} {url}" for _, title, url in sources]).lower()
        expected = [
            "metric views", "bi tools", "power bi", "semantic model", "directquery",
            "direct lake", "mirroring", "shortcut", "dashboard", "dashboard limits",
            "unity catalog", "fabric", "onelake",
        ]
        if not any(term in source_text for term in expected):
            source_coverage_warning += (
                "COMPETITIVE SOURCE WARNING:\n"
                "- Retrieved context may not include enough directly relevant connector, semantic model, Fabric, or dashboard-limit evidence.\n"
                "- Provide field guidance, but label source gaps clearly and avoid hard claims about roadmap, governance inheritance, or competitor limits.\n\n"
            )

    if topic == "powerbi_semantic_architecture":
        source_text = " ".join([f"{title} {url}" for _, title, url in sources]).lower()
        has_powerbi_source = "power bi" in source_text or "powerbi" in source_text
        has_fabric_source = "fabric" in source_text or "onelake" in source_text or "direct lake" in source_text
        has_databricks_source = "databricks" in source_text
        if not (has_powerbi_source and (has_fabric_source or has_databricks_source)):
            source_coverage_warning += (
                "SEMANTIC ARCHITECTURE SOURCE WARNING:\n"
                "- Retrieved context may not fully cover Power BI, Fabric, and Databricks-backed data together.\n"
                "- Make the architecture recommendation, but label source gaps clearly and require a proof of concept before customer commitment.\n\n"
            )

    cli_rule = ""
    if not is_cli_request(question):
        cli_rule = (
            "Do not include CLI, REST API, SDK, curl, Terraform, or Azure CLI commands unless needed for a simple validation check. "
            "UI, SQL, nslookup, and dbutils.fs.ls validation checks are acceptable when relevant.\n\n"
        )

    attachment_prompt = ""
    if attachment_context:
        attachment_prompt = (
            f"Attachment context:\n{attachment_context}\n\n"
            "Use the exact extracted attachment text as the primary symptom. "
            "Do not infer missing screenshot details.\n\n"
        )

    competitive_output_gate = ""
    if intent == "competitive_positioning":
        competitive_output_gate = (
            "CRITICAL COMPETITIVE OUTPUT GATE:\n"
            "- The first line of the answer must be exactly: 1. Situation Readout\n"
            "- Use all 12 numbered headings from the competitive deal-handling structure exactly as written.\n"
            "- Keep each section to 1-3 tight bullets unless the user asks for a full workshop document.\n"
            "- Do not rename, combine, omit, or reorder the 12 top-level headings.\n"
            "- Section 2 must be exactly '2. What The Customer Is Really Asking'; Section 6 must be exactly '6. Who Needs To Be On The Call'; Section 7 must be exactly '7. Customer-Ready Response'; Section 10 must be exactly '10. Landmines / What Not To Say'.\n"
            "- Do not use alternate top-level headings such as Scenario Evaluation, Who Should Be on the Call, or What To Say.\n"
            "- Do not include unsupported numeric/platform-scale/SLA claims such as 100K users, millions of users, 99.9% uptime, trillion queries, market share, or roadmap promises.\n"
            "- Do not claim a pattern is suitable for the customer's scale unless the answer frames it as something to validate in a proof of concept.\n"
            "- Use the customer-provided scale only as customer context, such as 'the customer says they have 17,000 Tableau users'.\n"
            "- Treat customer objections as legitimate until proven otherwise; separate legitimate concern from competitive framing.\n\n"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Selected product route: {selected_product}\n"
                f"Detected topic: {topic}\n"
                f"Detected intent: {intent}\n"
                f"Answer mode: {answer_mode}\n\n"
                f"Conversation history:\n{chat_history or 'No prior conversation.'}\n\n"
                f"Latest user request:\n{question}\n\n"
                f"{attachment_prompt}"
                f"{('Live status context:\n' + status_context + '\n\n') if status_context else ''}"
                f"Standalone retrieval query used:\n{retrieval_question}\n\n"
                f"Retrieved context:\n{context}\n\n"
                f"{followup_instruction}"
                f"{quality_instruction}"
                f"{customer_written_instruction}"
                f"{topic_instruction}"
                f"{source_coverage_warning}"
                f"{screenshot_triage_instruction}"
                f"{cli_rule}"
                f"{answer_format}\n"
                f"{competitive_output_gate}"
                "Be concise unless the user explicitly asks for hand-holding, end-to-end setup, full accuracy, question-by-question answers, or detailed troubleshooting. "
                "Avoid restating prior answers. "
                "If selected product route is Fabric, answer as a Microsoft Fabric SME and cite Fabric sources when available. Do not force Databricks concepts into Fabric unless the user asks for a Databricks comparison. "
                "If selected product route is Databricks, answer as an Azure Databricks SME and avoid Fabric-specific guidance unless relevant. "
                "If selected product route is Compare, answer as a cross-product Microsoft field strategist. Clearly separate Databricks, Fabric, and Power BI roles, when to use each, when they complement each other, and what to say to a customer. "
                "If this is an ADLS Gen2 private endpoint/private storage access request, clearly separate private endpoint/DNS, Access Connector/RBAC, and Unity Catalog storage credential/external location. "
                "If this is a Fabric mirroring request, do not give generic Unity Catalog external-location steps; provide a Fabric-owned mirroring setup flow. "
                "If this is a CSP/compliance architecture request, answer each embedded question one by one and separate platform behavior from compliance governance. "
                "If this is a cluster bootstrap/startup request, give a Databricks-specific runbook with exact UI locations, logs to inspect, likely causes, isolation tests, and validation steps. "
                "Use inline citations where helpful. Do not include a final Sources section."
            ),
        },
    ]

    selected_model = choose_chat_model(intent, topic)
    try:
        answer = predict_chat_text(messages, selected_model)
        answer = repair_answer_if_needed(answer, question, sources, intent, topic, selected_product, selected_model)
        answer = sanitize_csp_customer_email(answer, question, topic)
    except Exception as exc:
        answer = (
            "I could not complete the model response after retrying the configured serving endpoints.\n\n"
            f"Selected product route: `{selected_product}`\n"
            f"Detected topic: `{topic}`\n"
            f"Detected intent: `{intent}`\n\n"
            f"Model-serving detail: {exc}\n\n"
            "The retrieval layer did return context, so this is most likely a model-serving availability, timeout, permissions, or endpoint configuration issue."
        )

    return answer, sources, topic, intent


def regenerate_last_answer(k: int, answer_mode: str, product_mode: str) -> bool:
    if not st.session_state.get("pending_answer_mode_regeneration"):
        return False

    if not st.session_state.get("last_prompt_for_model"):
        st.session_state["pending_answer_mode_regeneration"] = False
        return False

    prompt_for_model = st.session_state.get("last_prompt_for_model", "")
    attachment_context = st.session_state.get("last_attachment_context", "")
    chat_history = st.session_state.get("last_chat_history", "")
    selected_product_route = resolve_product_route(
        prompt_for_model,
        attachment_context,
        product_mode,
        chat_history,
    )

    if (
        st.session_state.get("last_answer_mode") == answer_mode
        and st.session_state.get("last_product_route") == selected_product_route
    ):
        st.session_state["pending_answer_mode_regeneration"] = False
        return False

    route_label = product_mode if product_mode != "Auto" else selected_product_route.title()
    with st.spinner(f"Recompiling the last answer as {answer_mode} for {route_label}..."):
        answer, sources, topic, intent = ask_databricks_sme(
            prompt_for_model,
            k=k,
            answer_mode=answer_mode,
            product_mode=product_mode,
            chat_history=chat_history,
            attachment_context=attachment_context,
        )
        answer_with_links = add_clickable_citations(answer, sources)

    assistant_message = {
        "role": "assistant",
        "content": answer_with_links,
        "raw_content": answer,
        "question": prompt_for_model,
        "sources": sources,
        "topic": topic,
        "intent": intent,
        "answer_mode": answer_mode,
    }

    messages = st.session_state.get("messages", [])
    if messages and messages[-1].get("role") == "assistant":
        messages[-1] = assistant_message
    else:
        messages.append(assistant_message)
    st.session_state["messages"] = messages

    save_chat_message(
        session_id=st.session_state["session_id"],
        role="assistant",
        content=answer,
        topic=topic,
        intent=intent,
        sources=sources,
    )

    st.session_state["last_answer"] = answer
    st.session_state["last_sources"] = sources
    st.session_state["last_topic"] = topic
    st.session_state["last_intent"] = intent
    st.session_state["last_answer_mode"] = answer_mode
    st.session_state["last_product_route"] = selected_product_route
    st.session_state["last_answer_with_links"] = answer_with_links
    st.session_state["show_feedback_details"] = False
    st.session_state["pending_answer_mode_regeneration"] = False
    return True
