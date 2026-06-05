import os

import streamlit as st

try:
    from databricks.vector_search.client import VectorSearchClient
except Exception:
    VectorSearchClient = None

try:
    import mlflow.deployments
except Exception:
    mlflow = None

try:
    from databricks.sdk import WorkspaceClient
except Exception:
    WorkspaceClient = None

from app.config import (
    ACTIVE_DATABRICKS_AUTH_TYPE,
    DATABRICKS_AZURE_RESOURCE_ID,
    DATABRICKS_AZURE_TENANT_ID,
    DATABRICKS_CLIENT_ID,
    DATABRICKS_CLIENT_SECRET,
    DATABRICKS_HOST,
    DATABRICKS_TOKEN,
    ENABLE_FABRIC,
    ENABLE_POWERBI,
    FABRIC_VS_INDEX,
    POWERBI_VS_INDEX,
    VS_ENDPOINT,
    VS_INDEX,
)

@st.cache_resource
def get_clients():
    if WorkspaceClient is None:
        return None, None, None, "Missing package: databricks-sdk"

    if VectorSearchClient is None:
        return None, None, None, "Missing package: databricks-vectorsearch"

    if mlflow is None:
        return None, None, None, "Missing package: mlflow"

    if not DATABRICKS_HOST:
        return None, None, None, "Missing DATABRICKS_HOST or DATABRICKS_WORKSPACE_URL App Setting."

    if not ((DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET) or DATABRICKS_TOKEN):
        return None, None, None, "Missing Databricks credentials. Set DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET, or DATABRICKS_TOKEN."

    if (
        DATABRICKS_CLIENT_ID
        and DATABRICKS_CLIENT_SECRET
        and ACTIVE_DATABRICKS_AUTH_TYPE == "oauth-m2m"
        and not DATABRICKS_AZURE_TENANT_ID
    ):
        return (
            None,
            None,
            None,
            "Configured for oauth-m2m, but this looks like an Azure Entra service principal. "
            "Set DATABRICKS_AUTH_TYPE=azure-client-secret and DATABRICKS_AZURE_TENANT_ID=<your Entra tenant ID>.",
        )

    try:
        try:
            workspace_kwargs = {"host": DATABRICKS_HOST}
            if ACTIVE_DATABRICKS_AUTH_TYPE == "azure-client-secret":
                workspace_kwargs.update(
                    auth_type="azure-client-secret",
                    azure_tenant_id=DATABRICKS_AZURE_TENANT_ID,
                    azure_client_id=DATABRICKS_CLIENT_ID,
                    azure_client_secret=DATABRICKS_CLIENT_SECRET,
                )
                if DATABRICKS_AZURE_RESOURCE_ID:
                    workspace_kwargs["azure_workspace_resource_id"] = DATABRICKS_AZURE_RESOURCE_ID
            elif ACTIVE_DATABRICKS_AUTH_TYPE == "oauth-m2m":
                workspace_kwargs.update(
                    auth_type="oauth-m2m",
                    client_id=DATABRICKS_CLIENT_ID,
                    client_secret=DATABRICKS_CLIENT_SECRET,
                )
            elif ACTIVE_DATABRICKS_AUTH_TYPE == "pat":
                workspace_kwargs.update(auth_type="pat", token=DATABRICKS_TOKEN)

            workspace_client = WorkspaceClient(**workspace_kwargs)
        except Exception as exc:
            return (
                None,
                None,
                None,
                f"Workspace auth failed using {ACTIVE_DATABRICKS_AUTH_TYPE}: {exc}. "
                "For an Azure Entra service principal, use DATABRICKS_AUTH_TYPE=azure-client-secret, "
                "DATABRICKS_AZURE_TENANT_ID, DATABRICKS_CLIENT_ID, and DATABRICKS_CLIENT_SECRET.",
            )

        resolved_host = DATABRICKS_HOST or getattr(workspace_client.config, "host", "")
        if resolved_host and not resolved_host.startswith("http"):
            resolved_host = "https://" + resolved_host

        resolved_host = resolved_host.rstrip("/")

        if resolved_host:
            os.environ["DATABRICKS_HOST"] = resolved_host

        vs_kwargs = {"disable_notice": True}

        if resolved_host:
            vs_kwargs["workspace_url"] = resolved_host

        if DATABRICKS_TOKEN:
            vs_kwargs["personal_access_token"] = DATABRICKS_TOKEN
        elif ACTIVE_DATABRICKS_AUTH_TYPE != "azure-client-secret" and DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET:
            vs_kwargs["service_principal_client_id"] = DATABRICKS_CLIENT_ID
            vs_kwargs["service_principal_client_secret"] = DATABRICKS_CLIENT_SECRET

        try:
            vs_client = VectorSearchClient(**vs_kwargs)
            vector_index = vs_client.get_index(VS_ENDPOINT, VS_INDEX)
            fabric_vector_index = None
            powerbi_vector_index = None
            if ENABLE_FABRIC:
                try:
                    fabric_vector_index = vs_client.get_index(VS_ENDPOINT, FABRIC_VS_INDEX)
                except Exception:
                    fabric_vector_index = None
            if ENABLE_POWERBI:
                try:
                    powerbi_vector_index = vs_client.get_index(VS_ENDPOINT, POWERBI_VS_INDEX)
                except Exception:
                    powerbi_vector_index = None
        except Exception as exc:
            return None, None, workspace_client, f"Vector Search client failed using {ACTIVE_DATABRICKS_AUTH_TYPE}: {exc}"

        try:
            model_client = mlflow.deployments.get_deploy_client("databricks")
        except Exception as exc:
            return vector_index, None, workspace_client, f"Model serving client failed using {ACTIVE_DATABRICKS_AUTH_TYPE}: {exc}"

        return (vector_index, fabric_vector_index, powerbi_vector_index), model_client, workspace_client, ""

    except Exception as exc:
        return None, None, None, str(exc)


vector_indexes, deploy_client, workspace_client, CLIENT_INIT_ERROR = get_clients()
if isinstance(vector_indexes, tuple):
    vs_index = vector_indexes[0] if len(vector_indexes) > 0 else None
    fabric_vs_index = vector_indexes[1] if len(vector_indexes) > 1 else None
    powerbi_vs_index = vector_indexes[2] if len(vector_indexes) > 2 else None
else:
    vs_index, fabric_vs_index, powerbi_vs_index = vector_indexes, None, None
