# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Chunk & Embed: Microsoft Fabric Docs Corpus
# MAGIC ## Databricks Expert Assistant Project
# MAGIC
# MAGIC This notebook chunks and embeds the Fabric raw documentation corpus created by Notebook 1.
# MAGIC
# MAGIC **Input:** `chatbot.rag_chatbot.raw_docs_fabric`  
# MAGIC **Output:** `chatbot.rag_chatbot.doc_chunks_fabric`
# MAGIC
# MAGIC The current Databricks app chunk table is intentionally left untouched. Fabric chunks land separately first so we can validate quality, preserve product metadata, and avoid cross-product retrieval contamination.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load Configuration
# MAGIC
# MAGIC Use a Fabric-specific chunk table first. Later, once the app and Vector Search index are product-aware, we can merge Databricks and Fabric chunks into a unified table/index.

# COMMAND ----------

import os

CATALOG = os.getenv("RAG_CATALOG", "chatbot")
SCHEMA = os.getenv("RAG_SCHEMA", "rag_chatbot")

RAW_TABLE = os.getenv("FABRIC_RAW_TABLE", f"{CATALOG}.{SCHEMA}.raw_docs_fabric")
CHUNKS_TABLE = os.getenv("FABRIC_CHUNKS_TABLE", f"{CATALOG}.{SCHEMA}.doc_chunks_fabric")
UNIFIED_CHUNKS_TABLE = os.getenv("UNIFIED_CHUNKS_TABLE", f"{CATALOG}.{SCHEMA}.doc_chunks_all")

PRODUCT = "fabric"
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "databricks-gte-large-en")
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "25"))
BUILD_UNIFIED_CHUNKS_TABLE = os.getenv("BUILD_UNIFIED_CHUNKS_TABLE", "false").lower() == "true"

print(f"Source             : {RAW_TABLE}")
print(f"Fabric chunk target: {CHUNKS_TABLE}")
print(f"Unified target     : {UNIFIED_CHUNKS_TABLE}")
print(f"Chunks             : {CHUNK_SIZE} chars, {CHUNK_OVERLAP} overlap")
print(f"Embedding model    : {EMBED_MODEL}")
print(f"Embedding batch    : {EMBED_BATCH}")
print(f"Build unified      : {BUILD_UNIFIED_CHUNKS_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Import Required Libraries
# MAGIC
# MAGIC This notebook uses Spark for transformation and the Databricks Foundation Model API for embeddings.

# COMMAND ----------

from datetime import datetime

import mlflow.deployments
import pandas as pd
from pyspark.sql.functions import coalesce, col, concat, current_timestamp, length, lit, pandas_udf, posexplode, sha2, udf, when
from pyspark.sql.types import ArrayType, FloatType, StringType

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Validate Source and Target Tables
# MAGIC
# MAGIC Confirm the Fabric raw table exists and contains the metadata needed for product-aware retrieval.

# COMMAND ----------

required_columns = {"url", "title", "content"}
recommended_columns = {"product", "doc_family", "source", "source_type", "toc_url", "content_hash", "scraped_date"}

raw_df = spark.table(RAW_TABLE)
raw_columns = set(raw_df.columns)
missing_required = sorted(required_columns - raw_columns)
missing_recommended = sorted(recommended_columns - raw_columns)

if missing_required:
    raise ValueError(f"Missing required columns in {RAW_TABLE}: {missing_required}")

if missing_recommended:
    print(f"Warning: missing recommended metadata columns: {missing_recommended}")

source_page_count = raw_df.count()
print(f"Raw pages: {source_page_count:,}")
print(f"Columns  : {sorted(raw_df.columns)}")

if source_page_count == 0:
    raise ValueError(f"No rows found in {RAW_TABLE}. Run Notebook 1 first.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Normalize Metadata
# MAGIC
# MAGIC Older raw tables may not have all product-aware columns. This keeps the Fabric path resilient while making the output schema explicit.

# COMMAND ----------

if "product" not in raw_df.columns:
    raw_df = raw_df.withColumn("product", lit(PRODUCT))
else:
    raw_df = raw_df.withColumn("product", coalesce(col("product"), lit(PRODUCT)))

if "doc_family" not in raw_df.columns:
    raw_df = raw_df.withColumn("doc_family", lit("fabric"))
else:
    raw_df = raw_df.withColumn("doc_family", coalesce(col("doc_family"), lit("fabric")))

if "source" not in raw_df.columns:
    raw_df = raw_df.withColumn("source", lit("microsoft_learn"))
else:
    raw_df = raw_df.withColumn("source", coalesce(col("source"), lit("microsoft_learn")))

if "source_type" not in raw_df.columns:
    raw_df = raw_df.withColumn("source_type", lit("official_docs"))
else:
    raw_df = raw_df.withColumn("source_type", coalesce(col("source_type"), lit("official_docs")))

if "cloud" not in raw_df.columns:
    raw_df = raw_df.withColumn("cloud", lit("azure"))
else:
    raw_df = raw_df.withColumn("cloud", coalesce(col("cloud"), lit("azure")))

if "toc_url" not in raw_df.columns:
    raw_df = raw_df.withColumn("toc_url", lit(None).cast("string"))

if "content_hash" not in raw_df.columns:
    raw_df = raw_df.withColumn("content_hash", sha2(col("content"), 256))

if "scraped_date" not in raw_df.columns:
    raw_df = raw_df.withColumn("scraped_date", lit(None).cast("string"))

raw_df = raw_df.filter((col("content").isNotNull()) & (length(col("content")) > 100)).cache()
valid_page_count = raw_df.count()
print(f"Valid pages with content: {valid_page_count:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Define Chunking Logic
# MAGIC
# MAGIC This matches the Databricks app notebook: about 1,000 characters per chunk with a 200-character overlap.

# COMMAND ----------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    if not text or len(text) < 100:
        return []

    chunks = []
    step = chunk_size - overlap
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if len(chunk.strip()) > 100:
            chunks.append(chunk.strip())
        start += step

    return chunks

chunk_udf = udf(lambda text: chunk_text(text) if text else [], ArrayType(StringType()))
print("Chunk UDF defined.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Build Fabric Chunk Rows
# MAGIC
# MAGIC Every chunk keeps product and Fabric workload metadata so app routing can separate Fabric and Databricks answers.

# COMMAND ----------

chunks_df = (
    raw_df
    .select(
        "product",
        "doc_family",
        "source",
        "source_type",
        "cloud",
        "toc_url",
        "url",
        "title",
        "content_hash",
        "scraped_date",
        chunk_udf("content").alias("chunks"),
    )
    .select(
        "product",
        "doc_family",
        "source",
        "source_type",
        "cloud",
        "toc_url",
        "url",
        "title",
        "content_hash",
        "scraped_date",
        posexplode("chunks").alias("chunk_index", "chunk_text"),
    )
    .filter(length(col("chunk_text")) > 100)
)

chunks_df = chunks_df.withColumn(
    "chunk_id",
    concat(col("product"), lit("::"), col("url"), lit("::chunk::"), col("chunk_index").cast("string"))
).withColumn(
    "ingested_at",
    current_timestamp()
)

chunk_count = chunks_df.count()
print(f"Total chunks : {chunk_count:,}")
print(f"Avg per page : {chunk_count / valid_page_count:.1f}")

display(chunks_df.select(
    "chunk_id",
    "product",
    "doc_family",
    "url",
    "title",
    "source",
    "source_type",
    "cloud",
    "chunk_index",
    "chunk_text",
).limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Test Embedding Endpoint
# MAGIC
# MAGIC Fail fast before embedding the whole Fabric corpus.

# COMMAND ----------

deploy_client = mlflow.deployments.get_deploy_client("databricks")

try:
    test_response = deploy_client.predict(
        endpoint=EMBED_MODEL,
        inputs={"input": ["What is Microsoft Fabric OneLake and how does it work?"]},
    )
    embedding = test_response.data[0]["embedding"]
    print("API call succeeded")
    print(f"Embedding dimensions : {len(embedding)}")
    print(f"First 5 values       : {embedding[:5]}")
except Exception as exc:
    raise RuntimeError(f"Embedding endpoint test failed for '{EMBED_MODEL}': {exc}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Define Embedding UDF
# MAGIC
# MAGIC The pandas UDF batches calls to the Databricks embedding endpoint and returns a vector per chunk.

# COMMAND ----------

@pandas_udf(ArrayType(FloatType()))
def embed_udf(texts: pd.Series) -> pd.Series:
    client = mlflow.deployments.get_deploy_client("databricks")
    results = []
    batch = texts.tolist()

    for start in range(0, len(batch), EMBED_BATCH):
        sub_batch = batch[start:start + EMBED_BATCH]
        try:
            response = client.predict(
                endpoint=EMBED_MODEL,
                inputs={"input": sub_batch},
            )
            for item in response.data:
                results.append(item["embedding"])
        except Exception as exc:
            for _ in sub_batch:
                results.append(None)
            print(f"Embedding batch starting at {start} failed: {exc}")

    return pd.Series(results)

print("Embed UDF defined.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Embed Chunks
# MAGIC
# MAGIC This may take a while depending on the number of Fabric pages and endpoint throughput.

# COMMAND ----------

print(f"Embedding {chunk_count:,} Fabric chunks...")

embedded_df = chunks_df.withColumn("embedding", embed_udf(col("chunk_text")))
embedded_df = embedded_df.filter(col("embedding").isNotNull()).cache()

embedded_count = embedded_df.count()
failed_embedding_count = chunk_count - embedded_count

print(f"Embedded chunks : {embedded_count:,}")
print(f"Failed chunks   : {failed_embedding_count:,}")

if embedded_count == 0:
    raise RuntimeError("No Fabric chunks were embedded successfully.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Write Fabric Chunk Table
# MAGIC
# MAGIC This writes the Fabric-specific chunk table and leaves the existing Databricks `doc_chunks` table alone.

# COMMAND ----------

(
    embedded_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(CHUNKS_TABLE)
)

final_count = spark.table(CHUNKS_TABLE).count()
print(f"Written to : {CHUNKS_TABLE}")
print(f"Row count  : {final_count:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Post-Embedding Quality Checks
# MAGIC
# MAGIC Confirm embedding coverage, dimensions, duplicate chunk IDs, and product metadata coverage.

# COMMAND ----------

df = spark.table(CHUNKS_TABLE).cache()
null_embedding_count = df.filter(col("embedding").isNull()).count()
duplicate_chunk_id_count = df.groupBy("chunk_id").count().filter(col("count") > 1).count()
first_embedding = df.select("embedding").first()[0]
embedding_length = len(first_embedding) if first_embedding else 0

print(f"Total chunks        : {df.count():,}")
print(f"Null embeddings     : {null_embedding_count:,}")
print(f"Duplicate chunk IDs : {duplicate_chunk_id_count:,}")
print(f"Embedding length    : {embedding_length}")

assert null_embedding_count == 0, "Null embeddings found."
assert duplicate_chunk_id_count == 0, "Duplicate chunk IDs found."
assert embedding_length > 0, "Embedding vector is empty."

df.printSchema()
display(df.groupBy("product", "doc_family", "source", "source_type").count().orderBy("count", ascending=False))
display(df.select("product", "doc_family", "title", "chunk_index", "chunk_text").limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Optional Future Unified Chunk Table
# MAGIC
# MAGIC Keep this disabled until the app retrieval code and Vector Search index can filter or rank by `product`. Once ready, this can combine Databricks and Fabric chunks into one product-aware table.

# COMMAND ----------

DATABRICKS_CHUNKS_TABLE = f"{CATALOG}.{SCHEMA}.doc_chunks"

if BUILD_UNIFIED_CHUNKS_TABLE:
    databricks_chunks_df = spark.table(DATABRICKS_CHUNKS_TABLE)

    if "product" not in databricks_chunks_df.columns:
        databricks_chunks_df = databricks_chunks_df.withColumn("product", lit("databricks"))
    if "doc_family" not in databricks_chunks_df.columns:
        databricks_chunks_df = databricks_chunks_df.withColumn("doc_family", lit("azure_databricks"))
    if "cloud" not in databricks_chunks_df.columns:
        databricks_chunks_df = databricks_chunks_df.withColumn("cloud", lit("azure"))
    if "toc_url" not in databricks_chunks_df.columns:
        databricks_chunks_df = databricks_chunks_df.withColumn("toc_url", lit(None).cast("string"))
    if "content_hash" not in databricks_chunks_df.columns:
        databricks_chunks_df = databricks_chunks_df.withColumn("content_hash", lit(None).cast("string"))
    if "ingested_at" not in databricks_chunks_df.columns:
        databricks_chunks_df = databricks_chunks_df.withColumn("ingested_at", current_timestamp())

    fabric_chunks_df = spark.table(CHUNKS_TABLE)
    unified_df = databricks_chunks_df.unionByName(fabric_chunks_df, allowMissingColumns=True)

    (
        unified_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(UNIFIED_CHUNKS_TABLE)
    )

    print(f"Written unified chunk table: {UNIFIED_CHUNKS_TABLE}")
    display(spark.table(UNIFIED_CHUNKS_TABLE).groupBy("product", "source", "source_type").count())
else:
    print("Skipping unified chunk table build. Set BUILD_UNIFIED_CHUNKS_TABLE=true only after app routing is product-aware.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13. Log Chunking and Embedding Metrics
# MAGIC
# MAGIC Record counts and status for basic observability.

# COMMAND ----------

metrics_table = f"{CATALOG}.{SCHEMA}.rag_embedding_metrics"
run_id = datetime.utcnow().strftime("fabric_embed_%Y%m%d_%H%M%S")
status = "success" if failed_embedding_count == 0 else "completed_with_embedding_errors"

metrics_rows = [(
    run_id,
    PRODUCT,
    RAW_TABLE,
    CHUNKS_TABLE,
    str(source_page_count),
    str(valid_page_count),
    str(chunk_count),
    str(embedded_count),
    str(failed_embedding_count),
    EMBED_MODEL,
    status,
    datetime.utcnow().isoformat(),
)]

metrics_df = spark.createDataFrame(
    metrics_rows,
    [
        "run_id",
        "product",
        "raw_table",
        "chunks_table",
        "source_page_count",
        "valid_page_count",
        "chunk_count",
        "embedded_count",
        "failed_embedding_count",
        "embed_model",
        "status",
        "completed_at",
    ],
)

metrics_df.write.format("delta").mode("append").saveAsTable(metrics_table)
print(f"Logged embedding metrics to: {metrics_table}")
display(spark.table(metrics_table).orderBy(col("completed_at").desc()))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC
# MAGIC 1. Run this notebook after `raw_docs_fabric` exists.
# MAGIC 2. Create or refresh a Vector Search index for `doc_chunks_fabric`.
# MAGIC 3. Update the Streamlit app to route Fabric questions to Fabric chunks.
# MAGIC 4. When routing is validated, consider a unified `doc_chunks_all` table and a single product-aware Vector Search index.

