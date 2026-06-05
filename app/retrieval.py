import json
import os
import re

import streamlit as st

from app.clients import deploy_client, fabric_vs_index, powerbi_vs_index, vs_index, workspace_client
from app.config import (
    CHAT_MODEL,
    DOC_CHUNKS_TABLE,
    EMBED_MODEL,
    ENABLE_KEYWORD_SEARCH,
    ENABLE_PLAYBOOKS,
    FABRIC_DOC_CHUNKS_TABLE,
    FINAL_CONTEXT_K,
    KEYWORD_TOP_K,
    MAX_ATTACHMENT_CHARS,
    POWERBI_DOC_CHUNKS_TABLE,
    REASONING_MODEL,
    VECTOR_TOP_K,
)
from app.playbooks import PLAYBOOKS
from app.prompts import SYSTEM_PROMPT
from app.routing import detect_intent, detect_topic, is_customer_written_output_request
from app.topics import GLOBAL_BAD_TERMS, TOPIC_CONFIG

def choose_chat_model(intent: str, topic: str) -> str:
    selected_reasoning_model = st.session_state.get("reasoning_model_endpoint", REASONING_MODEL)

    if intent == "competitive_positioning":
        return CHAT_MODEL

    high_reasoning_intents = [
        "deep_architecture",
        "deep_explanation",
        "deep_implementation",
        "deep_integration",
        "deep_troubleshooting",
        "learning",
        "meeting_prep",
    ]
    high_reasoning_topics = [
        "compliance_architecture",
        "fabric_mirroring",
        "adls_private_access",
        "unity_catalog",
        "spark_performance",
    ]

    if intent in high_reasoning_intents or topic in high_reasoning_topics:
        return selected_reasoning_model

    return CHAT_MODEL


def predict_chat_text(messages, preferred_model: str) -> str:
    if deploy_client is None:
        raise RuntimeError("Databricks model client is not configured.")

    selected_reasoning_model = st.session_state.get("reasoning_model_endpoint", REASONING_MODEL)
    candidate_models = []
    for model_name in [preferred_model, selected_reasoning_model, REASONING_MODEL, CHAT_MODEL]:
        if model_name and model_name not in candidate_models:
            candidate_models.append(model_name)

    last_error = None
    for model_name in candidate_models:
        for _ in range(2):
            try:
                response = deploy_client.predict(endpoint=model_name, inputs={"messages": messages})
                return extract_model_text(response)
            except Exception as exc:
                last_error = exc

    raise RuntimeError(f"Model serving failed after fallback attempts: {last_error}")


def required_competitive_headings():
    return [
        "1. Situation Readout",
        "2. What The Customer Is Really Asking",
        "3. Competitive Motion / FUD Diagnosis",
        "4. Technical Truth Table",
        "5. Recommended Stance",
        "6. Who Needs To Be On The Call",
        "7. Customer-Ready Response",
        "8. Meeting Invite And Agenda",
        "9. Talk Track For The Call",
        "10. Landmines / What Not To Say",
        "11. Proof Points, Citations, And Evidence Gaps",
        "12. Internal Escalation And Next Actions",
    ]


def quality_issues_for_answer(answer: str, question: str, intent: str, topic: str, selected_product: str):
    issues = []
    text = answer or ""
    lower_answer = text.lower()
    lower_question = (question or "").lower()

    if intent == "competitive_positioning":
        stripped = text.strip()
        if not stripped.startswith("1. Situation Readout"):
            issues.append("Competitive answer must start with exact heading '1. Situation Readout'.")
        for heading in required_competitive_headings():
            if heading not in text:
                issues.append(f"Missing exact competitive heading: {heading}")
        forbidden_patterns = [
            r"\b100k\+?\b",
            r"\bmillions of users\b",
            r"\b99\.9%\b",
            r"\btrillion queries\b",
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, lower_answer, flags=re.IGNORECASE):
                issues.append("Contains unsupported scale/SLA/adoption claim.")
                break

    if topic == "compliance_architecture" and is_customer_written_output_request(question):
        risky_customer_email_patterns = [
            r"\bunaffected\b",
            r"\bno impact\b",
            r"\bdefinitive answers\b",
            r"\bworkspace-isolated\b",
            r"\benforcement boundary is limited\b",
            r"\bplatform enforcement is isolated\b",
            r"broader azure environment remains unaffected",
            r"\bnon[- ]databricks services\b[\s\S]{0,120}\b(unaffected|no impact|remain unaffected)\b",
            r"\bazure resource groups\b[\s\S]{0,120}\b(unaffected|no impact|remain unaffected)\b",
            r"\bcsp controls are contained within the databricks workspace boundary\b",
            r"\bthe compliance boundary is enforced at the databricks workspace level\b",
            r"\bdoes not impact other azure resource groups or non[- ]databricks services\b",
            r"\bstorage accounts, networking, and other azure services retain their existing configurations\b",
            r"\bno\s+-\s+csp controls are contained\b",
            r"\bno\s+-\s+.*\bremains unaffected\b",
            r"\bno\s+-\s+.*\bno impact\b",
        ]
        for pattern in risky_customer_email_patterns:
            if re.search(pattern, lower_answer, flags=re.IGNORECASE):
                issues.append(
                    "Customer CSP email overclaims impact boundaries. Replace blanket 'unaffected/no impact/contained' wording with 'does not automatically reconfigure or propagate, but shared data/access/networking/logging/compliance dependencies should be validated.'"
                )
                break

        if "shared backend storage" in lower_question or "shared storage" in lower_question or "shared infrastructure" in lower_question:
            if "compliance" in lower_answer and not any(term in lower_answer for term in [
                "shared data", "connected data", "dependencies", "validate", "review",
            ]):
                issues.append("Shared storage CSP answer needs a compliance dependency review caveat, not only workspace-scope language.")

    semantic_architecture_request = (
        selected_product in {"fabric", "compare"}
        and (intent in {"architecture", "deep_architecture"} or topic == "powerbi_semantic_architecture")
        and any(term in lower_question for term in [
            "direct lake", "directquery", "direct query", "import mode",
            "semantic model", "semantic models", "power bi", "powerbi", "fabric",
        ])
    )

    if semantic_architecture_request:
        required_terms = {
            "Direct Lake": "direct lake",
            "Import": "import",
            "DirectQuery": "directquery",
            "Governance/security boundary": "governance",
            "Databricks-backed considerations": "databricks",
            "Proof-of-concept checklist": "proof",
        }
        for label, token in required_terms.items():
            if token not in lower_answer:
                issues.append(f"Missing semantic architecture element: {label}")
        has_matrix = "|" in text or "decision matrix" in lower_answer or "table" in lower_answer
        if not has_matrix:
            issues.append("Missing decision matrix/table for Direct Lake vs Import vs DirectQuery.")
        if "unity catalog" in lower_question and "semantic" not in lower_answer:
            issues.append("Needs semantic governance boundary, not only data governance.")
        unsafe_direct_lake_patterns = [
            r"direct lake[^\n\.]{0,120}(connect|connects|connecting)[^\n\.]{0,120}(unity catalog|uc tables|databricks unity catalog)",
            r"direct lake[^\n\.]{0,120}(unity catalog tables|databricks-backed data)",
            r"recommended pattern is to use direct lake to connect to databricks",
        ]
        if any(re.search(pattern, lower_answer, flags=re.IGNORECASE) for pattern in unsafe_direct_lake_patterns):
            issues.append("Unsafe Direct Lake wording: explain the Fabric/OneLake access or materialization pattern before recommending Direct Lake for Databricks-origin data.")
        if "unity catalog" in lower_question and re.search(r"recommended[^\n\.]{0,160}(architecture|pattern|recommendation)[^\n\.]{0,160}direct lake", lower_answer, flags=re.IGNORECASE):
            issues.append("Blanket Direct Lake recommendation for Databricks Unity Catalog source data; make the recommendation conditional across DirectQuery, Import, and Direct Lake-over-Fabric/OneLake patterns.")

    return issues[:8]


def sanitize_csp_customer_email(answer: str, question: str, topic: str) -> str:
    if topic != "compliance_architecture" or not is_customer_written_output_request(question):
        return answer

    sanitized = answer or ""

    direct_replacements = {
        "definitive answers": "careful, implementation-oriented guidance",
        "definitive answer": "careful answer",
        "CSP is enforced per workspace": "CSP is configured per workspace",
        "workspace-isolated": "workspace-scoped",
        "Platform enforcement is isolated to the Databricks workspace where enabled": "Platform controls are applied in the Databricks workspace where CSP is enabled; connected data access paths and compliance dependencies should still be validated",
        "Platform enforcement is isolated to the specific Databricks workspace": "Platform controls are applied in the specific Databricks workspace; connected data access paths and compliance dependencies should still be validated",
        "No automatic configuration changes to other Azure resources or resource groups": "It does not automatically reconfigure other Azure resources or resource groups; shared dependencies should still be reviewed",
        "The compliance boundary is enforced at the Databricks workspace level": "The CSP platform controls apply at the Databricks workspace level; compliance scope should still be validated across shared data access paths",
        "Storage accounts, networking, and other Azure services retain their existing configurations": "CSP does not automatically change storage, networking, or other Azure service configurations; those dependencies should still be reviewed for compliance scope",
        "Existing VNets, NSGs, and Azure Monitor configurations are unaffected by CSP enablement": "CSP does not automatically change existing VNets, NSGs, or Azure Monitor configurations; those dependencies should still be reviewed for compliance scope",
        "These retain their existing access controls and configurations": "CSP does not automatically change those controls; they should still be reviewed for compliance scope",
        "The compliance controls and hardened compute image apply only within the specific Databricks workspace where CSP is enabled": "The compliance controls and hardened compute image are applied in the Databricks workspace where CSP is enabled",
        "CSP enables additional monitoring, hardened compute images, and compliance controls within the workspace boundary": "CSP enables additional monitoring, hardened compute images, and compliance controls in the Databricks workspace where it is enabled",
        "Workspace-scoped enforcement boundary": "Workspace-scoped platform controls",
        "workspace-scoped enforcement boundary": "workspace-scoped platform controls",
        "Other workspaces accessing the same ADLS Gen2 storage retain their existing configuration and access patterns": "CSP does not automatically change other workspaces that access the same ADLS Gen2 storage; validate whether those access paths require equivalent controls for regulated data",
        "Each workspace maintains independent CSP configuration regardless of shared storage access": "Each workspace has its own CSP configuration; shared storage access should still be reviewed against compliance requirements",
        "Multiple workspaces can access the same storage account with different CSP configurations": "A shared storage account can be accessed by workspaces with different CSP settings from a platform-configuration standpoint, but regulated-data access should be reviewed to determine whether equivalent controls are required",
    }

    for old, new in direct_replacements.items():
        sanitized = sanitized.replace(old, new)

    regex_replacements = [
        (
            r"(?m)(\*\*Q:[^\n]+?\*\*\s*)No\s*-\s*",
            r"\1",
        ),
        (
            r"(?m)(Q:[^\n]+?\?\s*)No\s*-\s*",
            r"\1",
        ),
        (
            r"No\s*-\s*CSP\s+is\s+(?:enforced|configured)\s+per\s+workspace\s+and\s+does\s+not\s+automatically\s+propagate\s+to\s+other\s+workspaces",
            "CSP is configured per workspace and does not automatically propagate to other workspaces",
        ),
        (
            r"No\s*-\s*CSP\s+can\s+be\s+enabled\s+selectively\s+per\s+workspace",
            "CSP can be enabled selectively per workspace from a platform-configuration standpoint",
        ),
        (
            r"No\s*-\s*CSP\s+enforcement\s+boundary\s+is\s+limited\s+to\s+the\s+specific\s+Databricks\s+workspace",
            "CSP does not automatically reconfigure other Azure resources; shared dependencies and compliance scope should still be validated",
        ),
        (
            r"No\s*-\s*CSP\s+does\s+not\s+automatically\s+configure\s+other\s+Azure\s+services",
            "CSP does not automatically configure other Azure services; connected services and compliance dependencies should still be validated",
        ),
        (
            r"Platform\s+Level:\s*CSP\s+is\s+workspace-scoped\s+with\s+no\s+automatic\s+propagation\s+to\s+shared\s+infrastructure",
            "Platform Level: CSP is workspace-scoped and does not automatically propagate to shared infrastructure; shared data access paths still need compliance review",
        ),
        (
            r"Platform\s+Level:\s*CSP\s+is\s+workspace-isolated\s+with\s+no\s+automatic\s+propagation\s+to\s+shared\s+infrastructure",
            "Platform Level: CSP is workspace-scoped and does not automatically propagate to shared infrastructure; shared data access paths still need compliance review",
        ),
        (
            r"\bNo\s+automatic\s+configuration\s+changes\s+to\s+other\s+Azure\s+resources\s+or\s+resource\s+groups\b",
            "It does not automatically reconfigure other Azure resources or resource groups; shared dependencies should still be reviewed",
        ),
    ]

    for pattern, replacement in regex_replacements:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    sanitized = re.sub(r"\bunaffected\b", "not automatically changed", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\bno impact\b", "no automatic configuration change", sanitized, flags=re.IGNORECASE)

    if any(term in (question or "").lower() for term in ["shared storage", "shared backend", "shared infrastructure"]):
        lower_sanitized = sanitized.lower()
        if "validation caveat" not in lower_sanitized and "compliance dependencies" not in lower_sanitized:
            sanitized += (
                "\n\nValidation caveat: Because the architecture includes shared storage or shared infrastructure, "
                "we should validate regulated-data access paths, identities, Unity Catalog permissions, networking, "
                "logging, monitoring, and the applicable compliance framework before treating the rollout as complete."
            )

    return sanitized


def repair_answer_if_needed(answer: str, question: str, sources, intent: str, topic: str, selected_product: str, selected_model: str) -> str:
    issues = quality_issues_for_answer(answer, question, intent, topic, selected_product)
    if not issues:
        return answer

    source_summary = "\n".join([f"{sid} {title} {url}" for sid, title, url in (sources or [])[:12]])
    repair_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Revise the answer below to fix the listed quality issues.\n"
                "Keep only claims supported by the existing answer or source list. Do not add unsupported numeric scale, SLA, roadmap, or benchmark claims.\n"
                "Preserve inline citations already present when possible. Return only the revised answer.\n\n"
                f"Selected product route: {selected_product}\n"
                f"Intent: {intent}\n"
                f"Topic: {topic}\n"
                f"Original user request:\n{question}\n\n"
                f"Quality issues to fix:\n- " + "\n- ".join(issues) + "\n\n"
                f"Source list:\n{source_summary}\n\n"
                f"Original answer:\n{answer}"
            ),
        },
    ]

    try:
        repaired = predict_chat_text(repair_messages, selected_model).strip()
        if repaired and len(quality_issues_for_answer(repaired, question, intent, topic, selected_product)) <= len(issues):
            return repaired
    except Exception:
        pass

    return answer


def extract_model_text(response) -> str:
    try:
        if hasattr(response, "to_dict"):
            response = response.to_dict()
    except Exception:
        pass

    if isinstance(response, str):
        return response

    if not isinstance(response, dict):
        return str(response)

    try:
        return response["choices"][0]["message"]["content"]
    except Exception:
        pass

    try:
        return response["choices"][0]["text"]
    except Exception:
        pass

    try:
        pred = response["predictions"][0]
        if isinstance(pred, str):
            return pred
        if isinstance(pred, dict):
            return pred.get("content") or pred.get("text") or str(pred)
    except Exception:
        pass

    for key in ["output_text", "text", "content"]:
        if key in response:
            return str(response[key])

    return str(response)


def parse_hit_row(row):
    title = row[0] if len(row) > 0 else ""
    url = row[1] if len(row) > 1 else ""
    text = row[2] if len(row) > 2 else ""
    score = row[3] if len(row) > 3 else None
    return title, url, text, score


def normalize_text_for_search(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\.\s]", " ", text or "").lower()


def extract_keyword_terms(question: str, max_terms: int = 12):
    q = normalize_text_for_search(question)

    important_patterns = [
        "permission_denied", "bootstrap", "csp", "hipaa", "fabric", "mirroring",
        "unity catalog", "external use schema", "external location", "write files", "read files",
        "sql warehouse", "vector search", "servicenow", "lakeflow",
        "power bi", "semantic model", "direct lake", "directquery", "direct query",
        "import mode", "composite model", "fabric capacity", "onelake", "dax",
        "row-level security", "object-level security", "databricks sql warehouse",
        "power bi connector", "databricks connector",
        "init script", "event log", "driver logs", "worker logs",
        "private endpoint", "private access", "public network access disabled",
        "adls gen2", "dfs", "blob",
        "privatelink.dfs.core.windows.net", "privatelink.blob.core.windows.net",
        "databricks_ui_api", "browser_auth", "dbx-pub", "dbx-priv",
        "delegated subnet", "access connector", "storage blob data contributor",
        "private dns", "storage account", "vnet", "subnet", "abfss",
    ]

    terms = []
    for pattern in important_patterns:
        if pattern in q and pattern not in terms:
            terms.append(pattern)

    for token in q.split():
        if len(token) >= 5 and token not in terms:
            terms.append(token)
        if len(terms) >= max_terms:
            break

    return terms[:max_terms]


def sql_escape(value: str) -> str:
    return (value or "").replace("'", "''")


def embed_query(text: str):
    if deploy_client is None:
        return []

    try:
        resp = deploy_client.predict(endpoint=EMBED_MODEL, inputs={"input": [text]})
        data = resp.data if hasattr(resp, "data") else resp["data"]
        return data[0]["embedding"]
    except Exception:
        return []


def is_relevant_source(title: str, url: str, topic: str, product: str = "databricks") -> bool:
    cfg = TOPIC_CONFIG.get(topic, {})
    combined = f"{title} {url}".lower()

    if product == "fabric":
        fabric_relevant_terms = [
            "fabric", "power bi", "powerbi", "semantic", "directquery",
            "direct lake", "import", "onelake", "databricks connector",
            "azure databricks connector", "dax",
        ]
        if "docs.databricks.com" in combined and topic != "powerbi_semantic_architecture":
            return False
        if "azure databricks" in combined and not any(term in combined for term in fabric_relevant_terms):
            return False

    if product == "powerbi":
        if "docs.databricks.com" in combined:
            return False
        if "azure databricks" in combined and "power bi" not in combined and "powerbi" not in combined:
            return False

    if any(term in combined for term in cfg.get("bad_terms", [])):
        return False

    if any(term in combined for term in GLOBAL_BAD_TERMS):
        return False

    return True


def vector_retrieve(question: str, topic: str, intent: str, k: int = VECTOR_TOP_K, product: str = "databricks"):
    if product == "fabric":
        selected_index = fabric_vs_index
    elif product == "powerbi":
        selected_index = powerbi_vs_index
    else:
        selected_index = vs_index

    if selected_index is None or deploy_client is None:
        return []

    cfg = TOPIC_CONFIG.get(topic, TOPIC_CONFIG["general"])
    expanded_queries = [q.format(question=question) for q in cfg["queries"]]

    if intent == "deep_integration":
        expanded_queries.extend([
            f"Microsoft Fabric mirror Azure Databricks Unity Catalog tables prerequisites setup validation {question}",
            f"Microsoft Fabric mirrored database Azure Databricks Unity Catalog step by step {question}",
        ])

    elif intent == "deep_architecture":
        expanded_queries.extend([
            f"Azure Databricks Compliance Security Profile workspace scoped behavior official documentation {question}",
            f"Databricks Compliance Security Profile shared storage workspace compliance boundary {question}",
        ])

    elif intent == "deep_troubleshooting":
        expanded_queries.extend([
            f"Azure Databricks troubleshooting private endpoint DNS VNet storage firewall Unity Catalog {question}",
            f"Azure Databricks cluster bootstrap error troubleshooting event log init script driver logs worker logs {question}",
        ])

    rows = []
    seen = set()

    for q in expanded_queries:
        try:
            emb = embed_query(q)
            hits = selected_index.similarity_search(
                query_vector=emb,
                columns=["title", "url", "chunk_text"],
                num_results=k,
            )

            for row in hits.get("result", {}).get("data_array", []):
                title, url, text, score = parse_hit_row(row)
                if not is_relevant_source(title, url, topic, product=product):
                    continue

                key = (url, text[:300])
                if key not in seen:
                    seen.add(key)
                    rows.append((title, url, text, score, "vector"))
        except Exception:
            continue

    return rows


def keyword_retrieve(question: str, topic: str, k: int = KEYWORD_TOP_K, product: str = "databricks"):
    if not ENABLE_KEYWORD_SEARCH:
        return []

    if workspace_client is None:
        return []

    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        return []

    terms = extract_keyword_terms(question)
    if not terms:
        return []

    like_clauses = []
    for term in terms:
        safe = sql_escape(term)
        like_clauses.append(f"lower(title) LIKE '%{safe}%'")
        like_clauses.append(f"lower(chunk_text) LIKE '%{safe}%'")

    where_clause = " OR ".join(like_clauses)

    if product == "fabric":
        chunks_table = FABRIC_DOC_CHUNKS_TABLE
    elif product == "powerbi":
        chunks_table = POWERBI_DOC_CHUNKS_TABLE
    else:
        chunks_table = DOC_CHUNKS_TABLE

    sql = f"""
    SELECT title, url, chunk_text
    FROM {chunks_table}
    WHERE {where_clause}
    LIMIT {int(k)}
    """

    try:
        resp = workspace_client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=sql,
            wait_timeout="15s",
        )

        data_array = []
        try:
            data_array = resp.result.data_array or []
        except Exception:
            try:
                data_array = resp.as_dict().get("result", {}).get("data_array", []) or []
            except Exception:
                data_array = []

        rows = []
        for row in data_array:
            title = row[0] if len(row) > 0 else ""
            url = row[1] if len(row) > 1 else ""
            text = row[2] if len(row) > 2 else ""
            if is_relevant_source(title, url, topic, product=product):
                rows.append((title, url, text, None, "keyword"))

        return rows

    except Exception:
        return []


def playbook_retrieve(topic: str, product: str = "databricks"):
    if not ENABLE_PLAYBOOKS:
        return []

    rows = []

    if product in {"fabric", "powerbi"} and topic not in {"fabric_mirroring", "powerbi_semantic_architecture"}:
        return rows

    if topic in PLAYBOOKS:
        rows.append((
            f"Curated playbook: {topic}",
            f"playbook://{topic}",
            PLAYBOOKS[topic],
            1.0,
            "playbook",
        ))

    return rows


def score_row_for_question(row, question: str, topic: str):
    title, url, text, raw_score, source_type = row
    q_terms = set(extract_keyword_terms(question, max_terms=14))
    combined = normalize_text_for_search(f"{title} {url} {text}")

    score = 0.0

    if source_type == "playbook":
        score += 10.0
    elif source_type == "keyword":
        score += 5.0
    elif source_type == "vector":
        score += 3.0

    for term in q_terms:
        if term in combined:
            score += 1.5

    if topic.replace("_", "-") in combined or topic.replace("_", " ") in combined:
        score += 2.0

    if "learn.microsoft.com" in combined or "docs.databricks.com" in combined:
        score += 1.0

    if topic == "powerbi_semantic_architecture":
        for term in [
            "power bi", "semantic model", "direct lake", "directquery",
            "import", "fabric", "onelake", "rls", "ols", "dax",
            "databricks sql", "connector", "capacity",
        ]:
            if term in combined:
                score += 1.1

    return score


def hybrid_retrieve(question: str, k: int = FINAL_CONTEXT_K, product: str = "databricks"):
    topic = detect_topic(question)
    intent = detect_intent(question)

    if product == "fabric" and topic == "general":
        fabric_text = question.lower()
        if any(term in fabric_text for term in ["mirror", "mirroring", "shortcut", "onelake"]):
            topic = "fabric_mirroring"

    if product in {"fabric", "compare"}:
        semantic_text = question.lower()
        if any(term in semantic_text for term in [
            "direct lake", "directquery", "direct query", "import mode",
            "semantic model", "semantic models", "power bi", "powerbi",
            "dax", "rls", "ols", "databricks-backed", "databricks backed",
        ]):
            topic = "powerbi_semantic_architecture"

    if product == "compare":
        vector_rows = (
            vector_retrieve(question, topic, intent, k=VECTOR_TOP_K, product="databricks")
            + vector_retrieve(question, topic, intent, k=VECTOR_TOP_K, product="fabric")
            + vector_retrieve(question, topic, intent, k=VECTOR_TOP_K, product="powerbi")
        )
        keyword_rows = (
            keyword_retrieve(question, topic, k=KEYWORD_TOP_K, product="databricks")
            + keyword_retrieve(question, topic, k=KEYWORD_TOP_K, product="fabric")
            + keyword_retrieve(question, topic, k=KEYWORD_TOP_K, product="powerbi")
        )
    elif product == "fabric":
        vector_rows = (
            vector_retrieve(question, topic, intent, k=VECTOR_TOP_K, product="fabric")
            + vector_retrieve(question, topic, intent, k=VECTOR_TOP_K, product="powerbi")
        )
        keyword_rows = (
            keyword_retrieve(question, topic, k=KEYWORD_TOP_K, product="fabric")
            + keyword_retrieve(question, topic, k=KEYWORD_TOP_K, product="powerbi")
        )
    else:
        vector_rows = vector_retrieve(question, topic, intent, k=VECTOR_TOP_K, product=product)
        keyword_rows = keyword_retrieve(question, topic, k=KEYWORD_TOP_K, product=product)
    playbook_rows = playbook_retrieve(topic, product=product)

    all_rows = []
    seen = set()

    for row in playbook_rows + keyword_rows + vector_rows:
        title, url, text, raw_score, source_type = row
        key = (url, text[:300])
        if key in seen:
            continue
        seen.add(key)
        all_rows.append(row)

    ranked = sorted(
        all_rows,
        key=lambda r: score_row_for_question(r, question, topic),
        reverse=True,
    )

    final_rows = ranked[:k]
    return topic, intent, final_rows


def build_context(rows):
    context_blocks = []
    sources = []

    for i, row in enumerate(rows):
        title, url, text, score, source_type = row
        source_id = f"[{i + 1}]"
        label = "Curated playbook" if source_type == "playbook" else source_type

        context_blocks.append(
            f"{source_id} {title}\n"
            f"Source type: {label}\n"
            f"URL: {url}\n"
            f"{text}"
        )

        sources.append((source_id, title, url))

    return "\n\n---\n\n".join(context_blocks), sources


def rewrite_question_for_retrieval(question: str, chat_history: str, product: str = "databricks") -> str:
    if not chat_history.strip():
        return question

    if deploy_client is None:
        return question

    if product == "compare":
        product_label = "Azure Databricks, Microsoft Fabric, and Power BI"
    elif product == "powerbi":
        product_label = "Power BI"
    elif product == "fabric":
        product_label = "Microsoft Fabric and Power BI"
    else:
        product_label = product.title()

    messages = [
        {
            "role": "system",
            "content": (
                f"Rewrite the latest user request into one standalone {product_label} documentation search query. "
                "If the route is Compare / Better Together, preserve the product names and include comparison, boundary, integration, or customer-positioning terms from the request. "
                "Respect the selected product route. If the route is Fabric / Power BI, keep follow-up questions in Microsoft Fabric or Power BI unless the latest request explicitly switches to Databricks. "
                "If the route is Databricks, keep follow-up questions in Azure Databricks unless the latest request explicitly switches to Fabric or Power BI. "
                "If the latest request changes topic from previous conversation, ignore unrelated earlier context. "
                "If the latest request is about ADLS Gen2 private endpoints/private storage access, focus on Databricks access to ADLS Gen2 storage account private endpoint dfs blob private DNS Unity Catalog Access Connector. "
                "If the latest request is about Fabric mirroring, focus on Microsoft Fabric mirroring from Azure Databricks Unity Catalog. "
                "If the user says Databricks or Unity Catalog is already set up, preserve that constraint. "
                "Do not answer. Return only the search query."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Conversation history:\n{chat_history}\n\n"
                f"Latest request:\n{question}\n\n"
                "Standalone search query:"
            ),
        },
    ]

    try:
        response = deploy_client.predict(endpoint=CHAT_MODEL, inputs={"messages": messages})
        rewritten = extract_model_text(response).strip()
        return rewritten or question
    except Exception:
        return question


def attachment_has_real_text(attachment_context: str) -> bool:
    if not attachment_context:
        return False

    bad_markers = [
        "ATTACHMENT_OCR_NOT_CONFIGURED",
        "ATTACHMENT_OCR_FAILED",
        "ATTACHMENT_OCR_ERROR",
        "ATTACHMENT_UNSUPPORTED_TYPE",
        "ATTACHMENT_TEXT_ERROR",
        "ATTACHMENT_TEXT_EMPTY",
    ]

    return not any(marker in attachment_context for marker in bad_markers)


def extract_json_object(text: str):
    text = (text or "").strip()

    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def normalize_triage_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [f"{key}: {val}" for key, val in value.items() if str(val).strip()]
    return [str(value).strip()] if str(value).strip() else []


def format_screenshot_triage(file_name: str, triage: dict) -> str:
    visible_text = str(triage.get("visible_text") or "").strip()
    product_area = str(triage.get("product_area") or "Unknown").strip()
    ui_area = str(triage.get("ui_area") or "Unknown").strip()
    detected_symptom = str(triage.get("detected_symptom") or "Unknown").strip()
    likely_topic = str(triage.get("likely_topic") or "general").strip()
    likely_intent = str(triage.get("likely_intent") or "deep_troubleshooting").strip()
    severity = str(triage.get("severity") or "unknown").strip()
    confidence = str(triage.get("confidence") or "unknown").strip()
    error_codes = normalize_triage_list(triage.get("error_codes"))
    object_names = normalize_triage_list(triage.get("object_names"))
    missing_info = normalize_triage_list(triage.get("missing_info"))
    first_checks = normalize_triage_list(triage.get("suggested_first_checks"))

    if not visible_text:
        visible_text = "No readable screenshot text was returned by the triage model."

    lines = [
        "SCREENSHOT_AUTO_TRIAGE",
        f"File: {file_name}",
        f"Product area: {product_area}",
        f"UI area: {ui_area}",
        f"Detected symptom: {detected_symptom}",
        f"Likely topic: {likely_topic}",
        f"Likely intent: {likely_intent}",
        f"Severity: {severity}",
        f"Confidence: {confidence}",
        f"Error codes: {', '.join(error_codes) if error_codes else 'None detected'}",
        f"Objects: {', '.join(object_names) if object_names else 'None detected'}",
        f"Missing info: {', '.join(missing_info) if missing_info else 'None identified'}",
        f"Suggested first checks: {', '.join(first_checks) if first_checks else 'None provided'}",
        "Visible text:",
        visible_text[:MAX_ATTACHMENT_CHARS],
    ]

    return "\n".join(lines)


def screenshot_triage_value(attachment_context: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", attachment_context or "", flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def screenshot_triage_metadata(attachment_context: str) -> dict:
    if "SCREENSHOT_AUTO_TRIAGE" not in (attachment_context or ""):
        return {}

    return {
        "product_area": screenshot_triage_value(attachment_context, "Product area"),
        "ui_area": screenshot_triage_value(attachment_context, "UI area"),
        "detected_symptom": screenshot_triage_value(attachment_context, "Detected symptom"),
        "likely_topic": screenshot_triage_value(attachment_context, "Likely topic"),
        "likely_intent": screenshot_triage_value(attachment_context, "Likely intent"),
        "severity": screenshot_triage_value(attachment_context, "Severity"),
        "confidence": screenshot_triage_value(attachment_context, "Confidence"),
        "error_codes": screenshot_triage_value(attachment_context, "Error codes"),
        "missing_info": screenshot_triage_value(attachment_context, "Missing info"),
        "suggested_first_checks": screenshot_triage_value(attachment_context, "Suggested first checks"),
    }


def build_retrieval_question(question: str, chat_history: str = "", attachment_context: str = "", product: str = "databricks") -> str:
    if st.session_state.get("answer_mode_label") == "Competitive / Customer Positioning":
        competitive_context = (
            "Power BI Databricks connector BI compatibility mode Unity Catalog Metric Views external BI tools "
            "Databricks AI BI dashboards dashboard limits Power BI semantic models DirectQuery Import mode Direct Lake "
            "Microsoft Fabric OneLake mirroring shortcuts governance security masking semantic layer enterprise BI Tableau replacement customer positioning."
        )
        question = f"{competitive_context}\n\nCustomer scenario or email chain:\n{question}"

    if attachment_has_real_text(attachment_context):
        triage = screenshot_triage_metadata(attachment_context)
        triage_context = ""

        if triage:
            triage_context = (
                f"Screenshot product area: {triage.get('product_area')}\n"
                f"Screenshot detected symptom: {triage.get('detected_symptom')}\n"
                f"Screenshot likely topic: {triage.get('likely_topic')}\n"
                f"Screenshot error codes/text: {triage.get('error_codes')}\n"
                f"Screenshot missing info: {triage.get('missing_info')}\n\n"
            )

        combined = (
            f"User question:\n{question}\n\n"
            f"{triage_context}"
            f"Visible/extracted attachment text:\n{attachment_context}\n\n"
            "Search for Azure Databricks or Microsoft Fabric troubleshooting documentation relevant to the exact visible error."
        )
        return rewrite_question_for_retrieval(combined, chat_history, product=product)

    return rewrite_question_for_retrieval(question, chat_history, product=product)
