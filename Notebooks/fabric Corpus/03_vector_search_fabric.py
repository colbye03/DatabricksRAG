# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Vector Search: Microsoft Fabric Docs Corpus
# MAGIC ## Databricks Expert Assistant Project
# MAGIC
# MAGIC This notebook creates or refreshes a Mosaic AI Vector Search Delta Sync index for the Fabric chunk table.
# MAGIC
# MAGIC **Input:** `chatbot.rag_chatbot.doc_chunks_fabric`  
# MAGIC **Output index:** `chatbot.rag_chatbot.doc_chunks_fabric_index`
# MAGIC
# MAGIC The Vector Search endpoint can be shared with the Databricks index, but the Fabric index stays separate until app routing is product-aware.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load Configuration
# MAGIC
# MAGIC The clean pipeline shape is:
# MAGIC
# MAGIC 1. `01_ingestion_fabric`
# MAGIC 2. `02_chunk_embed_fabric`
# MAGIC 3. `03_vector_search_fabric`
# MAGIC
# MAGIC Keep the Fabric index separate first. Later, a unified product-aware index can be introduced after app routing validates `product = fabric` vs `product = databricks` filtering.

# COMMAND ----------

import os

CATALOG = os.getenv("RAG_CATALOG", "chatbot")
SCHEMA = os.getenv("RAG_SCHEMA", "rag_chatbot")

CHUNKS_TABLE = os.getenv("FABRIC_CHUNKS_TABLE", f"{CATALOG}.{SCHEMA}.doc_chunks_fabric")
VS_ENDPOINT = os.getenv("VECTOR_SEARCH_ENDPOINT", "databricks-expert-endpoint")
VS_INDEX = os.getenv("FABRIC_VECTOR_SEARCH_INDEX", f"{CATALOG}.{SCHEMA}.doc_chunks_fabric_index")
UNIFIED_VS_INDEX = os.getenv("UNIFIED_VECTOR_SEARCH_INDEX", f"{CATALOG}.{SCHEMA}.doc_chunks_all_index")

EMBED_MODEL = os.getenv("EMBED_MODEL", "databricks-gte-large-en")
EMBED_COLUMN = os.getenv("EMBED_COLUMN", "embedding")
ID_COLUMN = os.getenv("ID_COLUMN", "chunk_id")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
PIPELINE_TYPE = os.getenv("VECTOR_SEARCH_PIPELINE_TYPE", "TRIGGERED")
RUN_MANUAL_SYNC = os.getenv("RUN_MANUAL_SYNC", "true").lower() == "true"
WAIT_FOR_READY = os.getenv("WAIT_FOR_READY", "true").lower() == "true"
INDEX_PROVISION_TIMEOUT_SECONDS = int(os.getenv("INDEX_PROVISION_TIMEOUT_SECONDS", "1800"))
INDEX_POLL_SECONDS = int(os.getenv("INDEX_POLL_SECONDS", "30"))

print(f"Endpoint        : {VS_ENDPOINT}")
print(f"Fabric index    : {VS_INDEX}")
print(f"Unified index   : {UNIFIED_VS_INDEX}")
print(f"Source table    : {CHUNKS_TABLE}")
print(f"Embedding model : {EMBED_MODEL}")
print(f"Embedding column: {EMBED_COLUMN}")
print(f"ID column       : {ID_COLUMN}")
print(f"Pipeline type   : {PIPELINE_TYPE}")
print(f"Run sync        : {RUN_MANUAL_SYNC}")
print(f"Wait for ready  : {WAIT_FOR_READY}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Import Required Libraries

# COMMAND ----------

import json
import time
from datetime import datetime

import requests
from databricks.vector_search.client import VectorSearchClient
from pyspark.sql.functions import col, length


def get_databricks_api_context():
    context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    return context.apiUrl().get().rstrip("/"), context.apiToken().get()


def invoke_serving_endpoint(endpoint_name: str, payload: dict):
    host, token = get_databricks_api_context()
    response = requests.post(
        f"{host}/serving-endpoints/{endpoint_name}/invocations",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def embed_query_text(query: str):
    response = invoke_serving_endpoint(EMBED_MODEL, {"input": [query]})
    return response["data"][0]["embedding"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Validate Fabric Chunk Table
# MAGIC
# MAGIC Confirm the Fabric chunk table exists, has embeddings, and preserves product-aware metadata.

# COMMAND ----------

required_columns = {ID_COLUMN, EMBED_COLUMN, "chunk_text", "url", "title"}
recommended_columns = {"product", "doc_family", "source", "source_type", "cloud", "toc_url", "content_hash"}

chunks_df = spark.table(CHUNKS_TABLE).cache()
columns = set(chunks_df.columns)
missing_required = sorted(required_columns - columns)
missing_recommended = sorted(recommended_columns - columns)

if missing_required:
    raise ValueError(f"Missing required columns in {CHUNKS_TABLE}: {missing_required}")

if missing_recommended:
    print(f"Warning: missing recommended metadata columns: {missing_recommended}")

row_count = chunks_df.count()
null_embeddings = chunks_df.filter(col(EMBED_COLUMN).isNull()).count()
duplicate_ids = chunks_df.groupBy(ID_COLUMN).count().filter(col("count") > 1).count()
first_embedding = chunks_df.select(EMBED_COLUMN).filter(col(EMBED_COLUMN).isNotNull()).first()
embedding_length = len(first_embedding[0]) if first_embedding else 0

print(f"Rows            : {row_count:,}")
print(f"Null embeddings : {null_embeddings:,}")
print(f"Duplicate IDs   : {duplicate_ids:,}")
print(f"Embedding length: {embedding_length}")

if row_count == 0:
    raise ValueError(f"No rows found in {CHUNKS_TABLE}. Run Notebook 2 first.")
if null_embeddings > 0:
    raise ValueError(f"Null embeddings found in {CHUNKS_TABLE}: {null_embeddings}")
if duplicate_ids > 0:
    raise ValueError(f"Duplicate {ID_COLUMN} values found in {CHUNKS_TABLE}: {duplicate_ids}")
if embedding_length != EMBEDDING_DIMENSION:
    raise ValueError(f"Embedding dimension mismatch. Expected {EMBEDDING_DIMENSION}, got {embedding_length}")

display(chunks_df.groupBy("product", "doc_family", "source", "source_type").count().orderBy("count", ascending=False))
display(chunks_df.select("product", "doc_family", "title", "url", length(col("chunk_text")).alias("chunk_chars")).limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Create or Reuse Vector Search Endpoint
# MAGIC
# MAGIC The endpoint is compute for similarity search. It can safely host both Databricks and Fabric indexes.

# COMMAND ----------

vsc = VectorSearchClient(disable_notice=True)

try:
    vsc.create_endpoint(
        name=VS_ENDPOINT,
        endpoint_type="STANDARD",
    )
    print(f"Endpoint '{VS_ENDPOINT}' created. Waiting for it to be ready...")
except Exception as exc:
    if "already exists" in str(exc).lower():
        print(f"Endpoint '{VS_ENDPOINT}' already exists. Skipping creation.")
    else:
        raise


def describe_index_status():
    desc = vsc.get_index(VS_ENDPOINT, VS_INDEX).describe()
    status = desc.get("status", {})
    detail = status.get("message") or status.get("detailed_state") or "provisioning..."
    ready = status.get("ready", False)
    indexed_rows = status.get("indexed_row_count")
    progress = status.get("triggered_update_status", {}).get("triggered_update_progress", {})
    return desc, status, detail, ready, indexed_rows, progress


def wait_for_index_to_accept_sync():
    if not WAIT_FOR_READY:
        print("Skipping pre-sync index readiness wait because WAIT_FOR_READY=false.")
        return

    deadline = time.time() + INDEX_PROVISION_TIMEOUT_SECONDS
    last_detail = None

    while time.time() < deadline:
        _, status, detail, ready, indexed_rows, progress = describe_index_status()
        if detail != last_detail:
            print(f"Index detail : {detail}")
            last_detail = detail
        print(f"Ready        : {ready}")
        print(f"Indexed rows : {indexed_rows}")
        if progress:
            print(f"Progress     : {progress.get('sync_progress_completion')}")
            print(f"Synced       : {progress.get('num_synced_rows')} / {progress.get('total_rows_to_sync')}")
        print("-" * 80)

        detail_text = str(detail).lower()
        state_text = str(status.get("detailed_state") or "").lower()
        if ready or "online" in detail_text or "ready" in detail_text or "online" in state_text:
            print("Index is ready or online enough to continue.")
            return

        time.sleep(INDEX_POLL_SECONDS)

    raise TimeoutError(f"Index {VS_INDEX} was not ready after {INDEX_PROVISION_TIMEOUT_SECONDS} seconds.")

if WAIT_FOR_READY:
    while True:
        endpoint = vsc.get_endpoint(VS_ENDPOINT)
        state = endpoint.get("endpoint_status", {}).get("state")
        print(f"Endpoint state: {state}")
        if state == "ONLINE":
            print("Endpoint is ONLINE")
            break
        time.sleep(20)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Enable Change Data Feed
# MAGIC
# MAGIC Delta Sync indexes need Change Data Feed on the source Delta table.

# COMMAND ----------

spark.sql(f"ALTER TABLE {CHUNKS_TABLE} SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')")
print(f"Change Data Feed enabled on {CHUNKS_TABLE}")

props = spark.sql(f"SHOW TBLPROPERTIES {CHUNKS_TABLE}").filter("key = 'delta.enableChangeDataFeed'")
display(props)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Inspect Catalog and Source Table
# MAGIC
# MAGIC This is useful when troubleshooting Unity Catalog permissions or Delta Sync issues.

# COMMAND ----------

display(spark.sql(f"SELECT * FROM system.information_schema.catalogs WHERE catalog_name = '{CATALOG}'"))
display(spark.sql(f"DESCRIBE TABLE EXTENDED {CHUNKS_TABLE}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Create or Reuse Fabric Delta Sync Index
# MAGIC
# MAGIC The Fabric index is separate from the Databricks index, but uses the same embedding column and primary key pattern.

# COMMAND ----------

try:
    index = vsc.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        index_name=VS_INDEX,
        source_table_name=CHUNKS_TABLE,
        pipeline_type=PIPELINE_TYPE,
        primary_key=ID_COLUMN,
        embedding_dimension=EMBEDDING_DIMENSION,
        embedding_vector_column=EMBED_COLUMN,
    )
    print(f"Index '{VS_INDEX}' created.")
except Exception as exc:
    if "already exists" in str(exc).lower():
        print(f"Index '{VS_INDEX}' already exists. Skipping creation.")
    else:
        raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Trigger Sync
# MAGIC
# MAGIC For `TRIGGERED` indexes, the Lakeflow pipeline can run this notebook every other day after chunking finishes.

# COMMAND ----------

idx = vsc.get_index(VS_ENDPOINT, VS_INDEX)

if RUN_MANUAL_SYNC:
    wait_for_index_to_accept_sync()
    for attempt in range(1, 4):
        try:
            print(f"Triggering Fabric Vector Search index sync, attempt {attempt}...")
            idx.sync()
            print("Sync triggered.")
            break
        except Exception as exc:
            message = str(exc)
            if "not ready" not in message.lower() or attempt == 3:
                raise
            print(f"Index is not ready for sync yet: {message}")
            print(f"Waiting {INDEX_POLL_SECONDS} seconds before retrying...")
            time.sleep(INDEX_POLL_SECONDS)
else:
    print("Skipping manual sync because RUN_MANUAL_SYNC=false.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Wait for Index Readiness
# MAGIC
# MAGIC This polls index status and sync progress. If you prefer Lakeflow not to wait, set `WAIT_FOR_READY=false`.

# COMMAND ----------

if WAIT_FOR_READY:
    while True:
        _, status, detail, ready, indexed_rows, progress = describe_index_status()

        print(f"Index detail : {detail}")
        print(f"Indexed rows : {indexed_rows}")
        if progress:
            print(f"Progress     : {progress.get('sync_progress_completion')}")
            print(f"Synced       : {progress.get('num_synced_rows')} / {progress.get('total_rows_to_sync')}")
        print("-" * 80)

        if ready:
            print("Index is READY")
            break

        completion = progress.get("sync_progress_completion") if progress else None
        if completion is not None and completion >= 0.999:
            print("Sync progress looks complete.")
            break

        time.sleep(30)
else:
    print("Skipping readiness wait because WAIT_FOR_READY=false.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Describe Index
# MAGIC
# MAGIC Print the full index description for troubleshooting and auditability.

# COMMAND ----------

desc = vsc.get_index(VS_ENDPOINT, VS_INDEX).describe()
print(json.dumps(desc, indent=2))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Validate Indexed Corpus Shape
# MAGIC
# MAGIC Confirm the source table still has the expected Fabric metadata distribution.

# COMMAND ----------

display(spark.sql(f"""
SELECT product, doc_family, source, source_type, COUNT(*) AS chunks
FROM {CHUNKS_TABLE}
GROUP BY product, doc_family, source, source_type
ORDER BY chunks DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Optional Similarity Search Smoke Test
# MAGIC
# MAGIC This tests the Fabric index after sync. This index stores precomputed embeddings, so the smoke test embeds the query first and searches with `query_vector`.

# COMMAND ----------

try:
    query_vector = embed_query_text("What is Microsoft Fabric OneLake?")

    results = vsc.get_index(VS_ENDPOINT, VS_INDEX).similarity_search(
        query_vector=query_vector,
        columns=["chunk_id", "product", "doc_family", "title", "url", "chunk_text"],
        num_results=5,
    )
    print(json.dumps(results, indent=2)[:5000])
except Exception as exc:
    print(f"Smoke test skipped or unsupported for this index configuration: {exc}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13. Log Vector Search Metrics
# MAGIC
# MAGIC Record source table, index path, endpoint, row count, and run status for observability.

# COMMAND ----------

metrics_table = f"{CATALOG}.{SCHEMA}.rag_vector_search_metrics"
run_id = datetime.utcnow().strftime("fabric_vs_%Y%m%d_%H%M%S")

metrics_rows = [(
    run_id,
    "fabric",
    CHUNKS_TABLE,
    VS_ENDPOINT,
    VS_INDEX,
    str(row_count),
    str(datetime.utcnow().isoformat()),
    "success",
)]

metrics_df = spark.createDataFrame(
    metrics_rows,
    ["run_id", "product", "chunks_table", "endpoint", "index_name", "source_row_count", "completed_at", "status"],
)

metrics_df.write.format("delta").mode("append").saveAsTable(metrics_table)
print(f"Logged Vector Search metrics to: {metrics_table}")
display(spark.table(metrics_table).orderBy(col("completed_at").desc()))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Recommended Lakeflow Layout
# MAGIC
# MAGIC Keep two clean product pipelines for now:
# MAGIC
# MAGIC **Databricks refresh**
# MAGIC 1. `01_ingestion`
# MAGIC 2. `02_chunk_embed`
# MAGIC 3. `03_vector_search`
# MAGIC
# MAGIC **Fabric refresh**
# MAGIC 1. `01_ingestion_fabric`
# MAGIC 2. `02_chunk_embed_fabric`
# MAGIC 3. `03_vector_search_fabric`
# MAGIC
# MAGIC This keeps failures isolated. After the app can route/filter by product reliably, add a small fourth orchestration notebook or Lakeflow task that builds a unified `doc_chunks_all` and unified index if you still want one retrieval surface.
