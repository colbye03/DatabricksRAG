# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Ingest: Microsoft Fabric Docs Corpus
# MAGIC
# MAGIC This notebook ingests Microsoft Fabric documentation from Microsoft Learn into a separate Delta raw table for the Databricks Expert Assistant.
# MAGIC
# MAGIC Primary output: `chatbot.rag_chatbot.raw_docs_fabric`
# MAGIC
# MAGIC Recommended strategy: land Fabric in a new table first, validate it, then merge into a product-aware chunk/index layer once downstream retrieval preserves `product`, `doc_family`, `source`, and `source_type`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load Configuration and Environment Variables
# MAGIC
# MAGIC Keep Fabric docs isolated in `raw_docs_fabric` until chunking, Vector Search, and app routing are product-aware.

# COMMAND ----------

import os

CATALOG = os.getenv("RAG_CATALOG", "chatbot")
SCHEMA = os.getenv("RAG_SCHEMA", "rag_chatbot")
VOLUME = os.getenv("RAG_VOLUME", "raw_docs")

PRODUCT = "fabric"
SOURCE = "microsoft_learn"
SOURCE_TYPE = "docs"

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
FABRIC_RAW_TABLE = os.getenv("FABRIC_RAW_TABLE", f"{CATALOG}.{SCHEMA}.raw_docs_fabric")
UNIFIED_RAW_TABLE = os.getenv("UNIFIED_RAW_TABLE", f"{CATALOG}.{SCHEMA}.raw_docs_all")
BUILD_UNIFIED_RAW_TABLE = os.getenv("BUILD_UNIFIED_RAW_TABLE", "false").lower() == "true"

print(f"Catalog          : {CATALOG}")
print(f"Schema           : {CATALOG}.{SCHEMA}")
print(f"Volume           : {VOLUME_PATH}")
print(f"Fabric raw table : {FABRIC_RAW_TABLE}")
print(f"Unified table    : {UNIFIED_RAW_TABLE}")
print(f"Build unified    : {BUILD_UNIFIED_RAW_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Install and Import Required Libraries
# MAGIC
# MAGIC Cluster libraries required if not already present: `requests`, `beautifulsoup4`, and `lxml`.

# COMMAND ----------

import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pyspark.sql.functions import col, length, lit, udf, when
from pyspark.sql.types import StructField, StructType, StringType

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Authenticate to Fabric and Source Systems
# MAGIC
# MAGIC Microsoft Learn documentation is public, so no Fabric workspace authentication is required for this docs corpus. The notebook uses the active Databricks identity to write Delta tables in Unity Catalog.

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")

print(f"Created/verified catalog: {CATALOG}")
print(f"Created/verified schema : {CATALOG}.{SCHEMA}")
print(f"Created/verified volume : {VOLUME_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Define Source Fabric Documentation Families
# MAGIC
# MAGIC Microsoft Learn does not expose one all-up `https://learn.microsoft.com/en-us/fabric/toc.json`. Fabric docs are split by workload family, so this notebook ingests the valid workload TOCs below.

# COMMAND ----------

FABRIC_TOC_SOURCES = [
    ("fundamentals", "https://learn.microsoft.com/en-us/fabric/fundamentals/toc.json", "https://learn.microsoft.com/en-us/fabric/fundamentals/"),
    ("admin", "https://learn.microsoft.com/en-us/fabric/admin/toc.json", "https://learn.microsoft.com/en-us/fabric/admin/"),
    ("data_engineering", "https://learn.microsoft.com/en-us/fabric/data-engineering/toc.json", "https://learn.microsoft.com/en-us/fabric/data-engineering/"),
    ("data_factory", "https://learn.microsoft.com/en-us/fabric/data-factory/toc.json", "https://learn.microsoft.com/en-us/fabric/data-factory/"),
    ("data_science", "https://learn.microsoft.com/en-us/fabric/data-science/toc.json", "https://learn.microsoft.com/en-us/fabric/data-science/"),
    ("data_warehouse", "https://learn.microsoft.com/en-us/fabric/data-warehouse/toc.json", "https://learn.microsoft.com/en-us/fabric/data-warehouse/"),
    ("real_time_intelligence", "https://learn.microsoft.com/en-us/fabric/real-time-intelligence/toc.json", "https://learn.microsoft.com/en-us/fabric/real-time-intelligence/"),
    ("onelake", "https://learn.microsoft.com/en-us/fabric/onelake/toc.json", "https://learn.microsoft.com/en-us/fabric/onelake/"),
    ("database", "https://learn.microsoft.com/en-us/fabric/database/toc.json", "https://learn.microsoft.com/en-us/fabric/database/"),
    ("mirroring", "https://learn.microsoft.com/en-us/fabric/mirroring/toc.json", "https://learn.microsoft.com/en-us/fabric/mirroring/"),
    ("cicd", "https://learn.microsoft.com/en-us/fabric/cicd/toc.json", "https://learn.microsoft.com/en-us/fabric/cicd/"),
    ("security", "https://learn.microsoft.com/en-us/fabric/security/toc.json", "https://learn.microsoft.com/en-us/fabric/security/"),
    ("governance", "https://learn.microsoft.com/en-us/fabric/governance/toc.json", "https://learn.microsoft.com/en-us/fabric/governance/"),
    ("workload_development_kit", "https://learn.microsoft.com/en-us/fabric/workload-development-kit/toc.json", "https://learn.microsoft.com/en-us/fabric/workload-development-kit/"),
]

print(f"Fabric TOC families configured: {len(FABRIC_TOC_SOURCES)}")
for doc_family, toc_url, _ in FABRIC_TOC_SOURCES:
    print(f"- {doc_family}: {toc_url}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Inspect Available Fabric TOCs and Schemas
# MAGIC
# MAGIC Fetch each TOC, normalize relative URLs, deduplicate pages, and show document counts by Fabric family.

# COMMAND ----------

def clean_url(url: str) -> str:
    return (url or "").split("?")[0].split("#")[0].strip().rstrip("/")


def normalize_href(href: str, base_url: str):
    if not href:
        return None
    absolute = clean_url(urljoin(base_url, href.strip()))
    parsed = urlparse(absolute)
    if parsed.scheme not in {"https", "http"}:
        return None
    if parsed.netloc.lower() != "learn.microsoft.com":
        return None
    if not parsed.path.startswith("/en-us/fabric"):
        return None
    return absolute


def extract_urls_from_toc_node(node, doc_family: str, toc_url: str, base_url: str, rows=None):
    if rows is None:
        rows = []
    if isinstance(node, dict):
        href = node.get("href")
        normalized = normalize_href(href, base_url) if href else None
        if normalized and not node.get("redirect"):
            rows.append({
                "product": PRODUCT,
                "doc_family": doc_family,
                "source": SOURCE,
                "source_type": SOURCE_TYPE,
                "toc_url": toc_url,
                "url": normalized,
            })
        for key in ("items", "children"):
            for child in node.get(key, []):
                extract_urls_from_toc_node(child, doc_family, toc_url, base_url, rows)
    elif isinstance(node, list):
        for item in node:
            extract_urls_from_toc_node(item, doc_family, toc_url, base_url, rows)
    return rows

# COMMAND ----------

all_rows = []
toc_failures = []

for doc_family, toc_url, base_url in FABRIC_TOC_SOURCES:
    try:
        print(f"Fetching {doc_family} TOC...")
        response = requests.get(toc_url, timeout=30, headers={"User-Agent": "FabricAgentProject/1.0"})
        response.raise_for_status()
        rows = extract_urls_from_toc_node(response.json(), doc_family, toc_url, base_url)
        print(f"  URLs found before dedupe: {len(rows):,}")
        all_rows.extend(rows)
    except Exception as exc:
        toc_failures.append((doc_family, toc_url, str(exc)[:500]))

seen_urls = set()
deduped_rows = []
for row in all_rows:
    if row["url"] in seen_urls:
        continue
    seen_urls.add(row["url"])
    deduped_rows.append(row)

print(f"TOC failures       : {len(toc_failures):,}")
print(f"URLs before dedupe : {len(all_rows):,}")
print(f"URLs after dedupe  : {len(deduped_rows):,}")

if toc_failures:
    display(spark.createDataFrame(toc_failures, ["doc_family", "toc_url", "error"]))

url_rows = [(r["product"], r["doc_family"], r["source"], r["source_type"], r["toc_url"], r["url"]) for r in deduped_rows]
urls_df = spark.createDataFrame(url_rows, ["product", "doc_family", "source", "source_type", "toc_url", "url"]).cache()

display(urls_df.groupBy("doc_family").count().orderBy("count", ascending=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Decide Target Table Strategy
# MAGIC
# MAGIC Use `chatbot.rag_chatbot.raw_docs_fabric` now. Use the existing `raw_docs` table only if schema, grain, keys, metadata, and app retrieval expectations are already compatible.
# MAGIC
# MAGIC For this project, the safer path is a Fabric-specific raw table first, then a unified product-aware chunk table/index later.

# COMMAND ----------

print(f"Selected target table: {FABRIC_RAW_TABLE}")
print("Strategy: new Fabric-specific raw table for validation and rollback isolation")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Read Data from Fabric Docs
# MAGIC
# MAGIC The selected source is the normalized Microsoft Learn URL list from the Fabric TOCs.

# COMMAND ----------

def scrape_doc_page(url: str, product: str, doc_family: str, source: str, source_type: str, toc_url: str):
    scraped_at = datetime.utcnow().isoformat()
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": "FabricAgentProject/1.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        for tag in soup(["script", "style", "noscript", "svg", "img"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else url
        main = soup.find("main") or soup.find("article") or soup.find("div", {"role": "main"}) or soup.body
        content = main.get_text(" ", strip=True) if main else ""
        content = " ".join(content.split())
        content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest() if content else None
        return (product, doc_family, source, source_type, toc_url, url, title, content, content_hash, "ok", scraped_at)
    except Exception as exc:
        return (product, doc_family, source, source_type, toc_url, url, None, None, None, f"error: {str(exc)[:500]}", scraped_at)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Validate Source Data
# MAGIC
# MAGIC Checks include URL count, duplicate URLs, and scrape success/failure status.

# COMMAND ----------

assert urls_df.count() > 0, "No Fabric URLs were extracted from the configured TOCs."
duplicate_url_count = urls_df.groupBy("url").count().filter(col("count") > 1).count()
assert duplicate_url_count == 0, f"Duplicate URLs found after dedupe: {duplicate_url_count}"
print("URL source validation passed.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Transform Data for App Compatibility
# MAGIC
# MAGIC The output schema aligns with the current raw docs pattern and adds product-aware metadata needed for safe multi-product retrieval.

# COMMAND ----------

result_schema = StructType([
    StructField("product", StringType(), True),
    StructField("doc_family", StringType(), True),
    StructField("source", StringType(), True),
    StructField("source_type", StringType(), True),
    StructField("toc_url", StringType(), True),
    StructField("url", StringType(), True),
    StructField("title", StringType(), True),
    StructField("content", StringType(), True),
    StructField("content_hash", StringType(), True),
    StructField("status", StringType(), True),
    StructField("scraped_date", StringType(), True),
])

scrape_udf = udf(scrape_doc_page, result_schema)
print(f"Scraping {urls_df.count():,} Fabric URLs across Spark workers...")

scraped_df = (
    urls_df
    .select(scrape_udf(col("url"), col("product"), col("doc_family"), col("source"), col("source_type"), col("toc_url")).alias("result"))
    .select("result.*")
)

ok_df = scraped_df.filter(col("status") == "ok").cache()
bad_df = scraped_df.filter(col("status") != "ok").cache()

source_count = urls_df.count()
ok_count = ok_df.count()
bad_count = bad_df.count()

print(f"Source URLs : {source_count:,}")
print(f"Successful  : {ok_count:,}")
print(f"Failed      : {bad_count:,}")

display(bad_df.groupBy("doc_family", "status").count().orderBy("count", ascending=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Write Data to Target Table
# MAGIC
# MAGIC Write only successfully scraped pages. The first pass uses overwrite to make the corpus reproducible.

# COMMAND ----------

(
    ok_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(FABRIC_RAW_TABLE)
)

print(f"Written to : {FABRIC_RAW_TABLE}")
print(f"Row count  : {spark.table(FABRIC_RAW_TABLE).count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Perform Post-Ingestion Quality Checks
# MAGIC
# MAGIC Validate row counts, schema, duplicate URLs, metadata coverage, and content length distribution.

# COMMAND ----------

fabric_df = spark.table(FABRIC_RAW_TABLE).cache()
target_count = fabric_df.count()
duplicate_target_url_count = fabric_df.groupBy("url").count().filter(col("count") > 1).count()
missing_content_count = fabric_df.filter((col("content").isNull()) | (length(col("content")) == 0)).count()

print(f"Target rows          : {target_count:,}")
print(f"Duplicate target URLs: {duplicate_target_url_count:,}")
print(f"Missing content rows : {missing_content_count:,}")

assert target_count == ok_count, "Target row count does not match successful scrape count."
assert duplicate_target_url_count == 0, "Duplicate URLs found in target table."
assert missing_content_count == 0, "Rows with missing content found in target table."

fabric_df.printSchema()
display(fabric_df.groupBy("product", "doc_family", "source", "source_type").count().orderBy("count", ascending=False))
display(fabric_df.select("doc_family", "title", "url", length(col("content")).alias("content_chars")).orderBy(col("content_chars").desc()))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Register or Refresh App Metadata
# MAGIC
# MAGIC The app should not point at Fabric until the chunking notebook and Vector Search index preserve `product` metadata. This records the new corpus and rollout status.

# COMMAND ----------

metadata_table = f"{CATALOG}.{SCHEMA}.rag_corpus_metadata"
metadata_rows = [(
    PRODUCT,
    FABRIC_RAW_TABLE,
    "raw",
    "pending_chunking",
    datetime.utcnow().isoformat(),
    "Fabric docs ingested. Enable app routing after product-aware chunking and Vector Search refresh."
)]

metadata_df = spark.createDataFrame(metadata_rows, ["product", "table_name", "layer", "status", "updated_at", "notes"])
metadata_df.write.format("delta").mode("append").saveAsTable(metadata_table)

print(f"Updated metadata table: {metadata_table}")
display(spark.table(metadata_table).orderBy(col("updated_at").desc()))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Optional Future Merge
# MAGIC
# MAGIC Leave this disabled until downstream retrieval routing is ready. The app should eventually use one product-aware chunk/index layer, but not by mixing raw tables before metadata is preserved.

# COMMAND ----------

DATABRICKS_RAW_TABLE = f"{CATALOG}.{SCHEMA}.raw_docs"

if BUILD_UNIFIED_RAW_TABLE:
    databricks_df = spark.table(DATABRICKS_RAW_TABLE)
    databricks_tagged_df = (
        databricks_df
        .withColumn("product", lit("databricks"))
        .withColumn("doc_family", lit("azure_databricks"))
        .withColumn("source", when(col("url").startswith("internal_wiki://"), lit("internal_wiki")).otherwise(lit("microsoft_learn")))
        .withColumn("source_type", when(col("url").startswith("internal_wiki://"), lit("tsg")).otherwise(lit("docs")))
        .withColumn("toc_url", lit(None).cast("string"))
        .withColumn("content_hash", lit(None).cast("string"))
    )
    fabric_tagged_df = spark.table(FABRIC_RAW_TABLE)
    unified_df = databricks_tagged_df.unionByName(fabric_tagged_df, allowMissingColumns=True)
    unified_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(UNIFIED_RAW_TABLE)
    print(f"Written unified raw table: {UNIFIED_RAW_TABLE}")
    display(spark.table(UNIFIED_RAW_TABLE).groupBy("product", "source", "source_type").count())
else:
    print("Skipping unified raw table build. Set BUILD_UNIFIED_RAW_TABLE=true only when downstream routing is ready.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13. Log Ingestion Metrics and Errors
# MAGIC
# MAGIC Capture source row count, target row count, rejected row count, ingestion status, and error details.

# COMMAND ----------

metrics_table = f"{CATALOG}.{SCHEMA}.rag_ingestion_metrics"
run_id = datetime.utcnow().strftime("fabric_docs_%Y%m%d_%H%M%S")
status = "success" if bad_count == 0 else "completed_with_errors"

metrics_rows = [(
    run_id,
    PRODUCT,
    SOURCE,
    FABRIC_RAW_TABLE,
    str(source_count),
    str(target_count),
    str(bad_count),
    status,
    datetime.utcnow().isoformat(),
)]

metrics_df = spark.createDataFrame(metrics_rows, ["run_id", "product", "source", "target_table", "source_row_count", "target_row_count", "rejected_row_count", "status", "completed_at"])
metrics_df.write.format("delta").mode("append").saveAsTable(metrics_table)

print(f"Logged ingestion metrics to: {metrics_table}")
display(spark.table(metrics_table).orderBy(col("completed_at").desc()))

if bad_count > 0:
    error_table = f"{CATALOG}.{SCHEMA}.rag_ingestion_errors"
    bad_df.withColumn("run_id", lit(run_id)).write.format("delta").mode("append").saveAsTable(error_table)
    print(f"Logged scrape errors to: {error_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC
# MAGIC 1. Run this notebook and validate `chatbot.rag_chatbot.raw_docs_fabric`.
# MAGIC 2. Update the chunking and embedding notebook to carry `product`, `doc_family`, `source`, and `source_type` onto every chunk.
# MAGIC 3. Create or refresh a product-aware Vector Search index.
# MAGIC 4. Update the app to route Fabric questions to Fabric chunks and keep Databricks questions pinned to Databricks chunks.

