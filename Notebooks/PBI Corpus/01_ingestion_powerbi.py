# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Ingestion: Power BI Docs Corpus
# MAGIC ## Databricks Expert Assistant Project
# MAGIC
# MAGIC This notebook ingests official Microsoft Learn Power BI, DAX, and Power Query documentation into a separate raw table for the Databricks + Fabric Expert Assistant.
# MAGIC
# MAGIC **Output:** `chatbot.rag_chatbot.raw_docs_powerbi`
# MAGIC
# MAGIC Power BI docs are intentionally kept separate from the Fabric and Databricks corpora first so the app can route or compare products without source contamination.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load Configuration

# COMMAND ----------

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from pyspark.sql.types import StringType, StructField, StructType

CATALOG = os.getenv("RAG_CATALOG", "chatbot")
SCHEMA = os.getenv("RAG_SCHEMA", "rag_chatbot")
RAW_TABLE = os.getenv("POWERBI_RAW_TABLE", f"{CATALOG}.{SCHEMA}.raw_docs_powerbi")

REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.15"))
MAX_PAGES_PER_TOC = int(os.getenv("MAX_PAGES_PER_TOC", "0"))
MIN_CONTENT_CHARS = int(os.getenv("MIN_CONTENT_CHARS", "400"))
USER_AGENT = os.getenv("DOCS_USER_AGENT", "DatabricksExpertAssistantPowerBIDocs/1.0")

POWERBI_TOC_SOURCES = [
    {
        "doc_family": "powerbi_fundamentals",
        "toc_url": "https://learn.microsoft.com/en-us/power-bi/fundamentals/toc.json",
        "base_url": "https://learn.microsoft.com/en-us/power-bi/fundamentals/",
    },
    {
        "doc_family": "powerbi_connect_data",
        "toc_url": "https://learn.microsoft.com/en-us/power-bi/connect-data/toc.json",
        "base_url": "https://learn.microsoft.com/en-us/power-bi/connect-data/",
    },
    {
        "doc_family": "powerbi_create_reports",
        "toc_url": "https://learn.microsoft.com/en-us/power-bi/create-reports/toc.json",
        "base_url": "https://learn.microsoft.com/en-us/power-bi/create-reports/",
    },
    {
        "doc_family": "powerbi_guidance",
        "toc_url": "https://learn.microsoft.com/en-us/power-bi/guidance/toc.json",
        "base_url": "https://learn.microsoft.com/en-us/power-bi/guidance/",
    },
    {
        "doc_family": "dax",
        "toc_url": "https://learn.microsoft.com/en-us/dax/toc.json",
        "base_url": "https://learn.microsoft.com/en-us/dax/",
    },
    {
        "doc_family": "power_query",
        "toc_url": "https://learn.microsoft.com/en-us/power-query/toc.json",
        "base_url": "https://learn.microsoft.com/en-us/power-query/",
    },
]

print(f"Raw target       : {RAW_TABLE}")
print(f"TOC sources      : {len(POWERBI_TOC_SOURCES)}")
print(f"Max pages per TOC: {MAX_PAGES_PER_TOC or 'unlimited'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Define TOC and Page Scrapers

# COMMAND ----------

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def get_json(url: str) -> dict:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def normalize_doc_url(href: str, base_url: str) -> str:
    if not href:
        return ""
    absolute = urljoin(base_url, href)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.netloc.lower() != "learn.microsoft.com":
        return ""
    if not parsed.path.lower().startswith("/en-us/"):
        return ""
    return absolute


def walk_toc_items(items, base_url: str, doc_family: str):
    docs = []
    for item in items or []:
        title = item.get("toc_title") or item.get("name") or item.get("title") or ""
        href = item.get("href") or ""
        url = normalize_doc_url(href, base_url)
        if url and not url.endswith("toc.json"):
            docs.append({"title": title, "url": url, "doc_family": doc_family})
        children = item.get("children") or item.get("items") or []
        docs.extend(walk_toc_items(children, base_url, doc_family))
    return docs


class LearnMainContentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.skip_depth = 0
        self.parts = []
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()
        attr_text = " ".join(str(value) for _, value in attrs if value)

        if tag_lower == "title":
            self.in_title = True

        if tag_lower == "main" or attrs_dict.get("id") == "main" or "content" in attrs_dict.get("class", ""):
            self.capture = True

        if self.capture and tag_lower in {"script", "style", "nav", "footer", "header", "svg", "noscript"}:
            self.skip_depth += 1

        if self.capture and self.skip_depth == 0 and tag_lower in {"p", "li", "h1", "h2", "h3", "h4", "td", "th", "pre", "code"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = False
        if self.skip_depth and tag_lower in {"script", "style", "nav", "footer", "header", "svg", "noscript"}:
            self.skip_depth -= 1
        if self.capture and self.skip_depth == 0 and tag_lower in {"p", "li", "h1", "h2", "h3", "h4", "tr", "pre"}:
            self.parts.append("\n")
        if tag_lower == "main":
            self.capture = False

    def handle_data(self, data):
        text = unescape(data or "").strip()
        if not text:
            return
        if self.in_title:
            self.title += f" {text}"
        if self.capture and self.skip_depth == 0:
            self.parts.append(text)

    def content(self):
        text = " ".join(self.parts)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([.,;:!?])", r"\1", text)
        return text.strip()


def scrape_doc_page(url: str) -> tuple:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    parser = LearnMainContentParser()
    parser.feed(response.text)
    content = parser.content()
    page_title = re.sub(r"\s+", " ", parser.title).strip()
    if " | " in page_title:
        page_title = page_title.split(" | ")[0].strip()
    return page_title, content

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Discover Pages from TOCs

# COMMAND ----------

all_docs = []
seen_urls = set()

for source in POWERBI_TOC_SOURCES:
    toc = get_json(source["toc_url"])
    items = toc.get("items") or toc.get("children") or []
    docs = walk_toc_items(items, source["base_url"], source["doc_family"])

    if MAX_PAGES_PER_TOC:
        docs = docs[:MAX_PAGES_PER_TOC]

    print(f"{source['doc_family']}: {len(docs):,} pages from {source['toc_url']}")

    for doc in docs:
        if doc["url"] in seen_urls:
            continue
        seen_urls.add(doc["url"])
        doc["toc_url"] = source["toc_url"]
        all_docs.append(doc)

print(f"Unique pages discovered: {len(all_docs):,}")

if not all_docs:
    raise ValueError("No Power BI documentation pages discovered from TOC sources.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Scrape Documentation Pages

# COMMAND ----------

rows = []
failures = []
scraped_at = datetime.now(timezone.utc).isoformat()

for index, doc in enumerate(all_docs, start=1):
    try:
        title, content = scrape_doc_page(doc["url"])
        title = title or doc.get("title") or doc["url"]
        if len(content) >= MIN_CONTENT_CHARS:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            rows.append({
                "product": "powerbi",
                "doc_family": doc["doc_family"],
                "source": "microsoft_learn",
                "source_type": "official_docs",
                "cloud": "fabric_powerbi",
                "toc_url": doc["toc_url"],
                "url": doc["url"],
                "title": title,
                "content": content,
                "content_hash": content_hash,
                "scraped_date": scraped_at,
            })
        else:
            failures.append({"url": doc["url"], "reason": f"content too short: {len(content)} chars"})
    except Exception as exc:
        failures.append({"url": doc["url"], "reason": str(exc)[:500]})

    if index % 50 == 0:
        print(f"Scraped {index:,}/{len(all_docs):,}; valid rows={len(rows):,}; failures={len(failures):,}")

    if REQUEST_SLEEP_SECONDS:
        time.sleep(REQUEST_SLEEP_SECONDS)

print(f"Valid pages : {len(rows):,}")
print(f"Failures    : {len(failures):,}")

if failures[:10]:
    print("Sample failures:")
    for failure in failures[:10]:
        print(json.dumps(failure, indent=2))

if not rows:
    raise ValueError("No valid Power BI documentation content was scraped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Write Raw Power BI Docs Table

# COMMAND ----------

schema = StructType([
    StructField("product", StringType(), True),
    StructField("doc_family", StringType(), True),
    StructField("source", StringType(), True),
    StructField("source_type", StringType(), True),
    StructField("cloud", StringType(), True),
    StructField("toc_url", StringType(), True),
    StructField("url", StringType(), True),
    StructField("title", StringType(), True),
    StructField("content", StringType(), True),
    StructField("content_hash", StringType(), True),
    StructField("scraped_date", StringType(), True),
])

raw_df = spark.createDataFrame(rows, schema=schema)

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

(raw_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(RAW_TABLE))

print(f"Wrote {raw_df.count():,} rows to {RAW_TABLE}")
display(raw_df.groupBy("product", "doc_family", "source", "source_type").count().orderBy("count", ascending=False))
display(raw_df.select("product", "doc_family", "title", "url").limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Notes
# MAGIC
# MAGIC Next notebooks:
# MAGIC
# MAGIC 1. `02_chunk_embed_powerbi`
# MAGIC 2. `03_vector_search_powerbi`
# MAGIC
# MAGIC Keep this corpus separate from Fabric docs. Power BI is related to Fabric, but Power BI has its own semantic model, DAX, report authoring, gateway, and service documentation that should be retrievable independently.

