import re

import streamlit as st

from app.config import ENABLE_FABRIC, ENABLE_POWERBI
from app.topics import TOPIC_CONFIG

def detect_topic(question: str) -> str:
    q = question.lower()

    ordered_topic_checks = [
        ("powerbi_semantic_architecture", TOPIC_CONFIG["powerbi_semantic_architecture"]["keywords"]),
        ("fabric_mirroring", TOPIC_CONFIG["fabric_mirroring"]["keywords"]),
        ("adls_private_access", TOPIC_CONFIG["adls_private_access"]["keywords"]),
        ("cluster_bootstrap", TOPIC_CONFIG["cluster_bootstrap"]["keywords"]),
        ("compliance_architecture", TOPIC_CONFIG["compliance_architecture"]["keywords"]),
        ("unity_catalog_setup", TOPIC_CONFIG["unity_catalog_setup"]["keywords"]),
        ("lakeflow_ingestion", TOPIC_CONFIG["lakeflow_ingestion"]["keywords"]),
        ("uc_external_storage", TOPIC_CONFIG["uc_external_storage"]["keywords"]),
        ("unity_catalog", TOPIC_CONFIG["unity_catalog"]["keywords"]),
        ("networking", TOPIC_CONFIG["networking"]["keywords"]),
        ("spark_performance", TOPIC_CONFIG["spark_performance"]["keywords"]),
        ("sql_warehouse", TOPIC_CONFIG["sql_warehouse"]["keywords"]),
        ("model_serving", TOPIC_CONFIG["model_serving"]["keywords"]),
        ("vector_search", TOPIC_CONFIG["vector_search"]["keywords"]),
        ("architecture", TOPIC_CONFIG["architecture"]["keywords"]),
    ]

    for topic, keywords in ordered_topic_checks:
        if any(keyword in q for keyword in keywords):
            return topic

    return "general"


def detect_product(question: str, attachment_context: str = "", product_mode: str = "Auto") -> str:
    if not ENABLE_FABRIC and not ENABLE_POWERBI:
        return "databricks"

    if product_mode in {"Power BI", "Fabric / Power BI"}:
        return "fabric"
    if product_mode in {"Databricks", "Fabric"}:
        return product_mode.lower()
    if product_mode == "Compare / Better Together":
        return "compare"

    text = f"{question}\n{attachment_context}".lower()
    if is_compare_request(text):
        return "compare"

    fabric_hits, databricks_hits, powerbi_hits = product_signal_counts(text)

    if (ENABLE_FABRIC or ENABLE_POWERBI) and max(fabric_hits, powerbi_hits) > databricks_hits:
        return "fabric"

    if ENABLE_FABRIC and fabric_hits > databricks_hits:
        return "fabric"
    return "databricks"


def resolve_product_route(question: str, attachment_context: str, product_mode: str, chat_history: str = "") -> str:
    if not ENABLE_FABRIC and not ENABLE_POWERBI:
        return "databricks"

    if product_mode in {"Power BI", "Fabric / Power BI"}:
        return "fabric"
    if product_mode in {"Databricks", "Fabric"}:
        return product_mode.lower()
    if product_mode == "Compare / Better Together":
        return "compare"

    latest_text = f"{question}\n{attachment_context}"
    if is_compare_request(latest_text):
        return "compare"

    fabric_hits, databricks_hits, powerbi_hits = product_signal_counts(latest_text)

    if (ENABLE_FABRIC or ENABLE_POWERBI) and max(fabric_hits, powerbi_hits) > databricks_hits:
        return "fabric"
    if databricks_hits > max(fabric_hits, powerbi_hits):
        return "databricks"

    last_product = st.session_state.get("last_product_route", "")
    if is_followup_question(question, chat_history) and last_product in {"fabric", "databricks", "powerbi", "compare"}:
        if last_product == "powerbi":
            return "fabric"
        return last_product

    if is_compare_request(chat_history):
        return "compare"

    history_fabric_hits, history_databricks_hits, history_powerbi_hits = product_signal_counts(chat_history)
    if (ENABLE_FABRIC or ENABLE_POWERBI) and max(history_fabric_hits, history_powerbi_hits) > history_databricks_hits:
        return "fabric"
    return "databricks"


def is_compare_request(text: str) -> bool:
    text = (text or "").lower()
    compare_terms = [
        "compare", "comparison", "versus", " vs ", "better together",
        "when to use databricks", "when to use fabric", "complement each other",
        "compliment each other", "competitive", "compete", "fud",
        "customer positioning", "positioning", "talk track", "what to say",
    ]
    has_compare_term = any(term in text for term in compare_terms)
    fabric_hits, databricks_hits, powerbi_hits = product_signal_counts(text)
    other_product_hits = fabric_hits + powerbi_hits
    return has_compare_term and databricks_hits > 0 and other_product_hits > 0


def product_signal_counts(text: str):
    text = (text or "").lower()
    fabric_terms = [
        "microsoft fabric", "fabric", "onelake", "semantic model",
        "capacity", "dataflow gen2", "real-time intelligence", "mirroring",
        "shortcut", "fabric pipeline", "fabric lakehouse", "fabric warehouse",
        "semantic layer", "semantic engine",
        "deployment pipeline", "fabric spark", "spark pool",
        "custom pool", "workspace pool", "fabric environment",
    ]
    databricks_terms = [
        "azure databricks", "databricks", "dbx", "cluster", "unity catalog", "dlt",
        "delta live tables", "auto loader", "sql warehouse", "photon", "dbsql",
        "lakeflow", "serving endpoint", "vector search", "metric views",
        "uc metric views", "ai/bi", "databricks connector",
    ]
    powerbi_terms = [
        "power bi", "powerbi", "power bi desktop", "power bi service",
        "semantic model", "dataset", "datasets", "dax", "power query",
        "m language", "pbix", "paginated report", "report builder",
        "gateway", "on-premises data gateway", "directquery", "import mode",
        "composite model", "power bi connector",
    ]

    fabric_hits = sum(1 for term in fabric_terms if term in text)
    databricks_hits = sum(1 for term in databricks_terms if term in text)
    powerbi_hits = sum(1 for term in powerbi_terms if term in text)
    return fabric_hits, databricks_hits, powerbi_hits


def detect_intent(question: str) -> str:
    q = question.lower()

    if any(x in q for x in [
        "customer meeting", "meeting prep", "prep for a call", "prepare for a call",
        "customer call", "customer conversation", "talk track", "what should i say",
        "how should i respond", "customer asked", "customer is asking", "upcoming call",
    ]):
        return "meeting_prep"

    if any(x in q for x in [
        "implement uc mirroring", "implement fabric mirroring",
        "setup fabric mirroring", "set up fabric mirroring",
        "mirror unity catalog", "mirroring unity catalog",
        "mirror databricks to fabric", "unity catalog to fabric",
        "first time person", "first time attempting",
    ]):
        return "deep_integration"

    if any(x in q for x in [
        "deep explanation", "deep explain", "explain deeply", "full explanation",
        "full super accurate", "super accurate", "break down", "breakdown",
        "one by one", "question by question", "each question", "answer all",
        "official documentation", "downstream impact", "all-or-nothing",
        "compliance boundary", "platform behavior",
    ]):
        return "deep_explanation"

    if any(x in q for x in [
        "asap", "clear steps", "clear instructions", "not generic",
        "very generic", "bootstrap error", "bootstrap failed",
        "cluster not starting", "cluster failed to start",
        "fails to start", "step by step troubleshoot",
        "help me resolve", "resolve the issue",
        "how do i resolve",
    ]):
        return "deep_troubleshooting"

    if any(x in q for x in [
        "hand holding", "hand-holding", "dont miss anything", "don't miss anything",
        "be precise", "from scratch", "beginner", "step by step assistance",
        "walk me through everything", "end to end", "end-to-end",
        "start from the beginning", "start from scratch", "be detailed", "full setup",
    ]):
        return "deep_implementation"

    if any(x in q for x in [
        "commands", "sql commands", "show me commands",
        "check permissions", "check grants", "show grants",
        "what commands", "verify permissions", "things to run",
        "run to check", "nslookup", "dbutils.fs.ls",
    ]):
        return "commands"

    if any(x in q for x in [
        "architecture", "architect", "solution architecture", "solution architect",
        "target architecture", "reference architecture", "design", "blueprint",
        "recommended architecture", "architecture plan",
    ]):
        return "architecture"

    if any(x in q for x in ["setup", "set up", "configure", "create", "implement", "getting started"]):
        return "implementation"

    if any(x in q for x in [
        "error", "fails", "failed", "failure", "wont", "won't",
        "can't", "cant", "cannot", "not working", "issue", "problem",
        "troubleshoot", "debug", "stuck", "pending", "permission denied",
        "permission_denied", "unauthorized access",
    ]):
        return "troubleshooting"

    if any(x in q for x in ["compare", "difference", "vs", "versus", "which is better"]):
        return "comparison"

    if any(x in q for x in [
        "what is", "teach me", "help me understand", "learn", "learning",
        "explain", "overview", "how does", "what does", "definition", "define",
    ]):
        return "learning"

    return "explanation"


def is_cli_request(question: str) -> bool:
    q = question.lower()
    return any(x in q for x in [
        "cli", "databricks cli", "rest api", "api call", "curl",
        "sdk", "python sdk", "terraform", "az cli", "azure cli",
    ])


def is_followup_question(question: str, chat_history: str) -> bool:
    if not chat_history.strip():
        return False

    q = question.lower().strip()
    return any(marker in q for marker in [
        "can you", "give me", "show me", "what about", "how about",
        "expand", "more detail", "commands", "sql", "that", "those",
        "it", "them", "this", "check", "verify", "now", "next",
        "actual steps", "things to run", "things to check", "mmm",
        "before i do that", "not generic", "very generic", "clear steps",
        "what?", "so how", "cool now", "ok i just",
    ])


def user_says_prereq_done(question: str, prereq: str) -> bool:
    q = (question or "").lower()

    if prereq == "unity_catalog":
        return any(x in q for x in [
            "databricks and unity catalog are already set up",
            "databricks and uc are already set up",
            "uc is already set up",
            "unity catalog is already set up",
            "databricks is fully set up",
            "databricks and uc are already operational",
            "uc already enabled",
            "unity catalog already enabled",
            "databricks and unity catalog are already configured",
        ])

    return False


def is_customer_written_output_request(question: str) -> bool:
    q = (question or "").lower()
    return any(marker in q for marker in [
        "customer email", "write an email", "email to customer", "customer-facing email",
        "customer ready email", "customer-ready email", "send to customer", "draft email",
        "customer written", "written email", "customer response email",
    ])


def build_customer_written_output_instruction(question: str, topic: str) -> str:
    if not is_customer_written_output_request(question):
        return ""

    instruction = (
        "CUSTOMER-WRITTEN OUTPUT RULES:\n"
        "- Write in customer-safe language suitable to paste into an email.\n"
        "- Do not include internal labels such as 'General SME guidance', 'source gaps', or diagnostic uncertainty unless rewritten as customer-safe validation language.\n"
        "- Do not use citation-heavy phrasing inside the email body. Put source references or evidence notes after the email if needed.\n"
        "- Avoid absolute reassurance such as 'unaffected', 'no impact', 'contained within the boundary', 'broader Azure environment remains unaffected', or 'does not affect any other services' unless the retrieved source explicitly supports that exact claim.\n"
        "- For CSP customer emails, avoid the word 'unaffected' entirely. Use 'not automatically reconfigured' or 'not automatically changed' plus a validation caveat.\n"
        "- Prefer conditional language: 'does not automatically change', 'does not automatically propagate', 'should still be reviewed for connected data flows, shared data access, monitoring, policy, and compliance requirements'.\n"
        "- Include a concise validation / next-step section so the customer knows what will be checked before a final architecture commitment.\n\n"
    )

    if topic == "compliance_architecture":
        instruction += (
            "CUSTOMER-WRITTEN CSP / COMPLIANCE RULES:\n"
            "- Separate Databricks platform configuration behavior from the customer's compliance control obligations.\n"
            "- Say CSP is workspace-scoped only if retrieved evidence supports it, and phrase it as 'workspace configuration does not automatically propagate' rather than 'other workspaces are unaffected'.\n"
            "- For shared storage, shared Unity Catalog/metastore, shared data, resource groups, networking, logging, or non-Databricks services, do not promise no impact. Say those dependencies should be reviewed because compliance scope can extend through shared data access or operational processes.\n"
            "- Do not say 'No - broader Azure environment remains unaffected'. Use: 'CSP does not automatically reconfigure other Azure resources; we should still validate connected services and compliance dependencies.'\n"
            "- Do not write 'networking and monitoring are unaffected' or 'storage accounts retain existing configuration' as an assurance. Use: 'CSP does not automatically change those configurations; we should validate shared dependencies and compliance scope.'\n"
            "- If a CSP setting is irreversible or hard to reverse, state that as a rollout planning consideration, not as a scare line.\n\n"
        )

    return instruction


def build_followup_instruction(question: str, chat_history: str, intent: str) -> str:
    if not is_followup_question(question, chat_history):
        return ""

    return (
        "FOLLOW-UP MODE:\n"
        "- This is a follow-up in an existing chat.\n"
        "- Do not repeat the previous answer.\n"
        "- Answer only the new request.\n"
        "- If the user says the prior answer was generic, switch to concrete steps/checks.\n"
        "- Use previous context only to resolve references.\n\n"
    )


def build_topic_instruction(topic: str, question: str) -> str:
    if topic == "powerbi_semantic_architecture":
        return (
            "TOPIC-SPECIFIC RULES: POWER BI / FABRIC SEMANTIC MODEL ARCHITECTURE\n"
            "- Treat this as an architecture decision, not a generic feature explanation.\n"
            "- Always separate Direct Lake, Import, DirectQuery, and Composite/Hybrid patterns when relevant.\n"
            "- For Direct Lake, discuss OneLake/Delta suitability, Fabric capacity, fallback behavior, supported tables/features, security validation, and semantic model constraints.\n"
            "- Do not say Direct Lake directly connects to Databricks Unity Catalog tables. For Databricks-origin data, identify the Fabric/OneLake access or materialization pattern first, then decide whether Direct Lake is valid over that Fabric-accessible Delta data.\n"
            "- For Import, discuss Power BI-managed cache/copy, scheduled or incremental refresh, fastest report interactivity, refresh reliability, data duplication, and Power BI-side security/model governance.\n"
            "- For DirectQuery, discuss live source queries, freshness, Databricks SQL warehouse sizing if Databricks-backed, source concurrency, query translation/folding, model limitations, and security behavior.\n"
            "- For Databricks-backed data, distinguish DirectQuery to Databricks SQL, Import from Databricks, Fabric mirrored database if supported, OneLake shortcut/read-access, and Direct Lake over Fabric-managed data.\n"
            "- For Databricks Unity Catalog source data, do not make Direct Lake the default recommendation. Recommend a conditional pattern: DirectQuery to Databricks SQL for live/source-governed access, Import for fastest controlled BI at refresh intervals, and Direct Lake only after the data is validly available in Fabric/OneLake and tested.\n"
            "- Explicitly separate Unity Catalog/source governance from Fabric workspace, OneLake, semantic model, RLS/OLS, endorsement/certification, deployment pipeline, and report-sharing governance.\n"
            "- Include a proof-of-concept checklist before recommending a customer commitment.\n\n"
        )

    if topic == "adls_private_access":
        return (
            "TOPIC-SPECIFIC RULES: DATABRICKS PRIVATE ACCESS TO ADLS GEN2\n"
            "- Do not confuse Databricks workspace private endpoints with storage account private endpoints.\n"
            "- If the user mentions databricks_ui_api or browser_auth, explain those are for private access to the Databricks workspace UI/API, not for Databricks compute accessing ADLS Gen2.\n"
            "- For private ADLS Gen2 access, focus on storage account private endpoints for dfs and usually blob.\n"
            "- Explain that private endpoints should be placed in a separate non-delegated subnet, not Dbx-Pub or Dbx-Priv delegated Databricks subnets.\n"
            "- Explain that Databricks can reach a private endpoint in a different subnet if it is in the same VNet or a peered/routable VNet.\n"
            "- Emphasize private DNS: privatelink.dfs.core.windows.net and privatelink.blob.core.windows.net must be linked to the Databricks compute VNet.\n"
            "- Explain that Databricks still uses the normal abfss URL; it should not use the privatelink hostname directly in the path.\n"
            "- Separate network path from identity permissions: private endpoint/DNS handles network, Access Connector/RBAC handles Azure permission, Unity Catalog storage credential/external location handles governance.\n"
            "- Include validation using nslookup and dbutils.fs.ls when troubleshooting.\n"
            "- If DNS resolves to a public IP, tell the user private DNS is not wired correctly.\n"
            "- If DNS resolves to a private IP but file access fails, tell the user to check RBAC, storage credential, external location, and grants.\n\n"
        )

    if topic == "fabric_mirroring":
        return (
            "TOPIC-SPECIFIC RULES: MICROSOFT FABRIC MIRRORING FROM AZURE DATABRICKS UNITY CATALOG\n"
            "- Treat this as a Microsoft Fabric-owned setup, not generic Unity Catalog external storage setup.\n"
            "- Start with a decision gate: does the user mean Fabric mirrored database / mirroring, or Fabric read access through OneLake shortcuts to Unity Catalog data?\n"
            "- Do not present OneLake shortcuts as equivalent to Fabric mirroring. If retrieved context supports shortcuts but not mirrored database replication, say so clearly.\n"
            "- Do NOT tell the user to create a Databricks external location, storage credential, or external table unless retrieved official context specifically says that is required.\n"
            "- If the user says Databricks or Unity Catalog is already set up, do not include metastore creation, workspace assignment, catalog creation, or schema creation steps.\n"
            "- Focus on Fabric workspace/capacity, Fabric mirrored database or shortcut experience, Azure Databricks connection, authentication/identity, catalog/schema/table selection, supported table requirements, refresh/replication behavior, and validation in OneLake/Fabric.\n"
            "- Include unsupported scenarios: views/materialized views/streaming tables/secured tables if retrieved context indicates limitations.\n"
            "- Explain governance caveat: Unity Catalog permissions control source access, but Fabric-side access, lineage, and downstream policy behavior must be validated separately.\n\n"
        )

    if topic == "cluster_bootstrap":
        return (
            "TOPIC-SPECIFIC RULES: DATABRICKS CLUSTER STARTUP / BOOTSTRAP\n"
            "- Do not give Spark performance tuning advice.\n"
            "- Start with Cluster Event Log, driver logs, worker logs, init script logs, and library events.\n"
            "- Give concrete UI checks and isolation tests.\n\n"
        )

    if topic == "compliance_architecture":
        return (
            "TOPIC-SPECIFIC RULES: CSP / COMPLIANCE ARCHITECTURE\n"
            "- Answer embedded questions one by one.\n"
            "- Separate platform enforcement from compliance governance.\n"
            "- Avoid overclaiming when docs do not explicitly cover the scenario.\n"
            "- Do not say 'zero downstream impact'; say there is no automatic configuration propagation, but connected data flows may still require compliance review.\n\n"
            "- Do not say other workspaces, Azure resource groups, or non-Databricks services are 'unaffected' or have 'no impact' without qualification. Safer wording: CSP does not automatically reconfigure them, but shared data, identities, networking, logging, monitoring, and compliance scope should be validated.\n"
            "- In a customer-facing email, avoid the word 'unaffected' entirely because it reads like a blanket assurance.\n"
            "- For shared backend storage or shared Unity Catalog/metastore scenarios, distinguish platform propagation from governance consistency. The platform setting may be workspace-scoped, while the customer's regulated-data policy may require equivalent controls across related workspaces.\n\n"
        )

    if topic == "unity_catalog":
        return (
            "TOPIC-SPECIFIC RULES: UNITY CATALOG LEARNING / ARCHITECTURE\n"
            "- Explain Unity Catalog as the governance layer for data and AI assets across Databricks workspaces.\n"
            "- Include the hierarchy: metastore > catalog > schema > table/view/function/model/volume.\n"
            "- Distinguish workspace-local concepts from account-level/metastore concepts.\n"
            "- Explain identity and permissions: users/groups/service principals receive privileges on securable objects.\n"
            "- Explain storage access separately: storage credential, external location, managed storage, external table, managed table.\n"
            "- Use a concrete example such as HR/Finance/Sales data with different access levels.\n\n"
        )

    if topic == "spark_performance":
        return (
            "TOPIC-SPECIFIC RULES: SPARK / NOTEBOOK PERFORMANCE\n"
            "- If the user asks whether you can optimize slow code, answer yes and explain exactly what inputs you need.\n"
            "- Do not pretend you can optimize unseen code; explain the optimization workflow and what evidence is required.\n"
            "- Prioritize Spark UI evidence: Jobs, Stages, SQL/DataFrame tab, task time, shuffle read/write, spill, skew, input size, executor metrics.\n"
            "- Separate code fixes from data layout fixes and cluster/runtime fixes.\n"
            "- Mention common fixes only with the symptom they address: broadcast joins, predicate pushdown, column pruning, repartition/coalesce, caching, Delta OPTIMIZE, liquid clustering/ZORDER, small-file compaction, avoiding collect/toPandas on large data.\n\n"
        )

    return ""


def build_quality_instruction(intent: str, topic: str, answer_mode: str) -> str:
    instruction = (
        "FIELD-READY 9/10 QUALITY CONTRACT:\n"
        "- The requested structure is mandatory. Use the section headings from the selected answer mode unless the user asks for a different format.\n"
        "- Do not give a generic textbook answer. Make the answer useful to someone doing real Azure Databricks work.\n"
        "- Start with the direct answer or key mental model in the first 2-3 sentences.\n"
        "- Include the practical 'so what': why the user/customer should care, what decision it affects, and what can go wrong.\n"
        "- Name concrete Databricks/Azure objects, UI areas, privileges, logs, metrics, or validation checks instead of vague wording.\n"
        "- Where the user asks a broad conceptual question, teach from simple mental model to real implementation details.\n"
        "- Where the user asks a troubleshooting/performance question, give a ranked diagnostic path, required evidence, likely causes, fixes, and validation.\n"
        "- Where the user asks for customer meeting prep, include exact words to say, a safe stance, 'If challenged', 'Avoid saying', and risk language that does not overclaim.\n"
        "- Where the user asks if something is possible, answer yes/no first, then explain the conditions, inputs needed, and limits.\n"
        "- Include examples that are specific enough to be useful: object hierarchy, sample flow, example symptoms, or example access model.\n"
        "- Avoid absolutes like 'zero impact', 'always', 'never', or 'guaranteed' unless directly supported by retrieved context.\n"
        "- If retrieved context is thin, clearly label 'General SME guidance' and provide a safe checklist instead of pretending it is official.\n"
        "- End with the next best action or what the user should bring/provide next.\n\n"
    )

    if intent == "competitive_positioning" or answer_mode == "Competitive / Customer Positioning":
        instruction += (
            "COMPETITIVE FIELD RESPONSE QUALITY CONTRACT:\n"
            "- Start with a scenario readout before giving advice.\n"
            "- Separate legitimate customer architecture concerns from competitor framing.\n"
            "- Name who should be on the call by role and why they are needed.\n"
            "- If the user included a draft, say whether to send it as-is and provide a safer rewrite.\n"
            "- Include exact customer-ready wording, meeting agenda, talk track, landmines, evidence gaps, and next owners.\n"
            "- Correct risky technical assumptions instead of repeating them.\n\n"
        )

    return instruction

# =============================================================================
