import os

# =============================================================================
# 02. APP CONFIG
# =============================================================================
CATALOG = "chatbot"
SCHEMA = "rag_chatbot"

VS_ENDPOINT = os.getenv("VECTOR_SEARCH_ENDPOINT", "databricks-expert-endpoint")
VS_INDEX = os.getenv("VECTOR_SEARCH_INDEX", f"{CATALOG}.{SCHEMA}.doc_chunks_index")
FABRIC_VS_INDEX = os.getenv("FABRIC_VECTOR_SEARCH_INDEX", f"{CATALOG}.{SCHEMA}.doc_chunks_fabric_index")
POWERBI_VS_INDEX = os.getenv("POWERBI_VECTOR_SEARCH_INDEX", f"{CATALOG}.{SCHEMA}.doc_chunks_powerbi_index")
DOC_CHUNKS_TABLE = os.getenv("DOC_CHUNKS_TABLE", f"{CATALOG}.{SCHEMA}.doc_chunks")
FABRIC_DOC_CHUNKS_TABLE = os.getenv("FABRIC_DOC_CHUNKS_TABLE", f"{CATALOG}.{SCHEMA}.doc_chunks_fabric")
POWERBI_DOC_CHUNKS_TABLE = os.getenv("POWERBI_DOC_CHUNKS_TABLE", f"{CATALOG}.{SCHEMA}.doc_chunks_powerbi")

CHAT_MODEL = os.getenv("CHAT_MODEL", "databricks-meta-llama-3-3-70b-instruct")
REASONING_MODEL = os.getenv("REASONING_MODEL", CHAT_MODEL)
CONFIGURED_REASONING_MODEL_OPTIONS = [
    option.strip()
    for option in os.getenv("REASONING_MODEL_OPTIONS", "").split(",")
    if option.strip()
]


def unique_model_options(options):
    unique = []
    for option in options:
        if option and option not in unique:
            unique.append(option)
    return unique


REASONING_MODEL_OPTIONS = unique_model_options(
    [
        REASONING_MODEL,
        "databricks-claude-sonnet-4",
        "databricks-claude-sonnet-4-5",
        "databricks-claude-sonnet-4-6",
        "databricks-claude-haiku-4-5",
        "databricks-claude-opus-4-1",
        "databricks-claude-opus-4-5",
        "databricks-claude-opus-4-6",
        "databricks-claude-opus-4-7",
        "databricks-llama-4-maverick",
        "databricks-meta-llama-3.1-405b-instruct",
        "databricks-meta-llama-3-1-8b-instruct",
        CHAT_MODEL,
        "databricks-meta-llama-3-3-70b-instruct",
        "databricks-gpt-oss-120b",
        "databricks-gpt-oss-20b",
        "databricks-gemma-3-12b",
        "databricks-qwen35-122b-a10b",
        "databricks-qwen3-next-80b-a3b-instruct",
    ]
    + CONFIGURED_REASONING_MODEL_OPTIONS
)
EMBED_MODEL = os.getenv("EMBED_MODEL") or os.getenv("EMBEDDING_MODEL") or "databricks-gte-large-en"
SCREENSHOT_MODEL = os.getenv("SCREENSHOT_MODEL", "")

FEEDBACK_TABLE = f"{CATALOG}.{SCHEMA}.answer_feedback"
CHAT_SESSIONS_TABLE = f"{CATALOG}.{SCHEMA}.chat_sessions"
LOG_CHAT_TRANSCRIPT = os.getenv("LOG_CHAT_TRANSCRIPT", "false").lower() == "true"
FEEDBACK_LOGGING_ENABLED = False
STATUS_DISPLAY_TIMEZONE_NAME = "America/Chicago"
STATUS_PREVIEW_ENABLED = os.getenv("STATUS_PREVIEW_ENABLED", "false").lower() == "true"
STATUS_PREVIEW_REGION = os.getenv("STATUS_PREVIEW_REGION", "Central US")
STATUS_PREVIEW_SERVICE = os.getenv("STATUS_PREVIEW_SERVICE", "Azure Databricks")

MAX_ATTACHMENT_CHARS = 12000
MAX_HISTORY_MESSAGES = 8
MAX_HISTORY_CHARS_PER_MESSAGE = 900

VECTOR_TOP_K = int(os.getenv("VECTOR_TOP_K", "5"))
KEYWORD_TOP_K = int(os.getenv("KEYWORD_TOP_K", "8"))
FINAL_CONTEXT_K = int(os.getenv("FINAL_CONTEXT_K", "12"))

ENABLE_KEYWORD_SEARCH = os.getenv("ENABLE_KEYWORD_SEARCH", "true").lower() == "true"
ENABLE_PLAYBOOKS = os.getenv("ENABLE_PLAYBOOKS", "true").lower() == "true"
ENABLE_FABRIC = os.getenv("ENABLE_FABRIC", "false").lower() == "true"
ENABLE_POWERBI = os.getenv("ENABLE_POWERBI", "false").lower() == "true"

# =============================================================================
# 03. DATABRICKS AUTH
# =============================================================================
# Azure App Service should provide these as App Settings:
# - DATABRICKS_HOST or DATABRICKS_WORKSPACE_URL
# - For an Entra ID service principal on Azure Databricks:
#   DATABRICKS_AUTH_TYPE=azure-client-secret
#   DATABRICKS_AZURE_TENANT_ID, AZURE_TENANT_ID, or ARM_TENANT_ID
#   DATABRICKS_AZURE_RESOURCE_ID or AZURE_DATABRICKS_RESOURCE_ID
#   DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET, or DATABRICKS_AZURE_CLIENT_ID + DATABRICKS_AZURE_CLIENT_SECRET
# - For PAT auth: DATABRICKS_TOKEN
DATABRICKS_HOST = (
    os.environ.get("DATABRICKS_HOST")
    or os.environ.get("DATABRICKS_WORKSPACE_URL")
    or ""
)

DATABRICKS_AUTH_TYPE = os.environ.get("DATABRICKS_AUTH_TYPE", "").strip()
DATABRICKS_AZURE_TENANT_ID = (
    os.environ.get("DATABRICKS_AZURE_TENANT_ID")
    or os.environ.get("AZURE_TENANT_ID")
    or os.environ.get("ARM_TENANT_ID")
    or ""
).strip()
DATABRICKS_AZURE_RESOURCE_ID = (
    os.environ.get("DATABRICKS_AZURE_RESOURCE_ID")
    or os.environ.get("AZURE_DATABRICKS_RESOURCE_ID")
    or os.environ.get("ARM_DATABRICKS_RESOURCE_ID")
    or ""
).strip()
DATABRICKS_CLIENT_ID = (
    os.environ.get("DATABRICKS_CLIENT_ID")
    or os.environ.get("DATABRICKS_AZURE_CLIENT_ID")
    or os.environ.get("ARM_CLIENT_ID")
    or ""
).strip()
DATABRICKS_CLIENT_SECRET = (
    os.environ.get("DATABRICKS_CLIENT_SECRET")
    or os.environ.get("DATABRICKS_AZURE_CLIENT_SECRET")
    or os.environ.get("ARM_CLIENT_SECRET")
    or ""
).strip()
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "") or os.environ.get("DATABRICKS_PAT", "")

if DATABRICKS_HOST and not DATABRICKS_HOST.startswith("http"):
    DATABRICKS_HOST = "https://" + DATABRICKS_HOST

DATABRICKS_HOST = DATABRICKS_HOST.rstrip("/")

if DATABRICKS_HOST:
    os.environ["DATABRICKS_HOST"] = DATABRICKS_HOST

if DATABRICKS_CLIENT_ID:
    os.environ["DATABRICKS_CLIENT_ID"] = DATABRICKS_CLIENT_ID

if DATABRICKS_CLIENT_SECRET:
    os.environ["DATABRICKS_CLIENT_SECRET"] = DATABRICKS_CLIENT_SECRET

if DATABRICKS_AZURE_TENANT_ID:
    os.environ["DATABRICKS_AZURE_TENANT_ID"] = DATABRICKS_AZURE_TENANT_ID
    os.environ["ARM_TENANT_ID"] = DATABRICKS_AZURE_TENANT_ID

if DATABRICKS_AZURE_RESOURCE_ID:
    os.environ["DATABRICKS_AZURE_RESOURCE_ID"] = DATABRICKS_AZURE_RESOURCE_ID
    os.environ["AZURE_DATABRICKS_RESOURCE_ID"] = DATABRICKS_AZURE_RESOURCE_ID

if DATABRICKS_CLIENT_ID:
    os.environ["DATABRICKS_AZURE_CLIENT_ID"] = DATABRICKS_CLIENT_ID
    os.environ["ARM_CLIENT_ID"] = DATABRICKS_CLIENT_ID

if DATABRICKS_CLIENT_SECRET:
    os.environ["DATABRICKS_AZURE_CLIENT_SECRET"] = DATABRICKS_CLIENT_SECRET
    os.environ["ARM_CLIENT_SECRET"] = DATABRICKS_CLIENT_SECRET

if DATABRICKS_TOKEN:
    os.environ["DATABRICKS_TOKEN"] = DATABRICKS_TOKEN

if DATABRICKS_AUTH_TYPE:
    os.environ["DATABRICKS_AUTH_TYPE"] = DATABRICKS_AUTH_TYPE
elif DATABRICKS_AZURE_TENANT_ID and DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET:
    os.environ["DATABRICKS_AUTH_TYPE"] = "azure-client-secret"
elif DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET and not os.environ.get("DATABRICKS_AUTH_TYPE"):
    os.environ["DATABRICKS_AUTH_TYPE"] = "oauth-m2m"
elif DATABRICKS_TOKEN and not os.environ.get("DATABRICKS_AUTH_TYPE"):
    os.environ["DATABRICKS_AUTH_TYPE"] = "pat"

ACTIVE_DATABRICKS_AUTH_TYPE = os.environ.get("DATABRICKS_AUTH_TYPE", "auto")

if ACTIVE_DATABRICKS_AUTH_TYPE == "azure-client-secret":
    # The Databricks SDK's Azure service-principal auth resolver expects ARM_* /
    # azure_* credential names. If the generic DATABRICKS_CLIENT_ID/SECRET remain
    # in the process environment, some SDK versions interpret them as Databricks
    # OAuth M2M fields instead of Azure SP fields and fail with
    # "cannot configure default credentials".
    os.environ.pop("DATABRICKS_CLIENT_ID", None)
    os.environ.pop("DATABRICKS_CLIENT_SECRET", None)

