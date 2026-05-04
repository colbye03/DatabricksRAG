# Databricks + Fabric RAG Expert Assistant

A source-backed RAG assistant for Azure Databricks, Microsoft Fabric, and Power BI field guidance.

This repository contains the corpus-building notebooks and notebook-style scripts that prepare the Databricks, Fabric, and Power BI knowledge sources used by the live assistant. The Fabric app slot uses these product-specific corpora to answer architecture, troubleshooting, implementation, customer-prep, and cross-product comparison questions with retrieved documentation context.

## Live App

| App | Purpose | URL |
| --- | --- | --- |
| Fabric slot | Combined Databricks + Fabric + Power BI assistant | `https://dbx-fabric-hbbghpckhgd7dec0.centralus-01.azurewebsites.net/` |

The Fabric slot is the main team-facing demo experience because it exposes Databricks, Fabric, Power BI, and Compare / Better Together routing in one app.

## Repository Scope

This repo currently focuses on the RAG data layer:

- Databricks documentation ingestion, chunking, embedding, and Vector Search indexing.
- Microsoft Fabric documentation ingestion, chunking, embedding, and Vector Search indexing.
- Power BI, DAX, and Power Query documentation ingestion, chunking, embedding, and Vector Search indexing.
- Product-separated Delta tables and Vector Search indexes so the app can retrieve the right evidence for the right product lens.

The deployed Streamlit app consumes the outputs of these pipelines through Databricks Vector Search and model-serving configuration. The app source and Azure App Service deployment package are not currently stored in this repository.

## High-Level Architecture

```text
Microsoft Learn docs + optional internal Databricks wiki
  |
  v
Product-specific ingestion notebooks/scripts
  |
  v
Raw Delta tables in Unity Catalog
  |
  v
Chunking and embedding with databricks-gte-large-en
  |
  v
Product-specific chunk Delta tables
  |
  v
Databricks Vector Search Delta Sync indexes
  |
  v
Fabric-slot Streamlit assistant
  |
  v
Source-backed field-ready answer
```

Core design principle:

> Keep product corpora separate first, then let the app route questions to the correct retrieval index.

That avoids a common multi-product RAG failure mode: giving a confident answer from the wrong product documentation.

## Repository Layout

```text
DatabricksRAG/
  README.md
  Notebooks/
    Databricks Corpus/
      01_ingestion.ipynb
      02_chunk_embed.ipynb
      03_vector_search.ipynb
    fabric Corpus/
      01_ingestion_fabric.py
      02_chunk_embed_fabric.py
      03_vector_search_fabric.py
    PBI Corpus/
      01_ingestion_powerbi.py
      02_chunk_embed_powerbi.py
      03_vector_search_powerbi.py
```

The Fabric and Power BI files are Databricks notebook exports in `.py` format. They still use Databricks notebook cell markers such as `# COMMAND ----------` and `%md` markdown cells.

## Pipeline Summary

| Product corpus | Ingest output | Chunk output | Vector Search index |
| --- | --- | --- | --- |
| Databricks | `chatbot.rag_chatbot.raw_docs` | `chatbot.rag_chatbot.doc_chunks` | `chatbot.rag_chatbot.doc_chunks_index` |
| Fabric | `chatbot.rag_chatbot.raw_docs_fabric` | `chatbot.rag_chatbot.doc_chunks_fabric` | `chatbot.rag_chatbot.doc_chunks_fabric_index` |
| Power BI | `chatbot.rag_chatbot.raw_docs_powerbi` | `chatbot.rag_chatbot.doc_chunks_powerbi` | `chatbot.rag_chatbot.doc_chunks_powerbi_index` |

All three pipelines use the same default catalog and schema:

```text
Catalog: chatbot
Schema : rag_chatbot
Vector Search endpoint: databricks-expert-endpoint
Embedding model: databricks-gte-large-en
Embedding dimension: 1024
Chunk size: 1000 characters
Chunk overlap: 200 characters
Embedding batch size: 25
```

## Databricks Corpus Pipeline

Location: `Notebooks/Databricks Corpus/`

The Databricks corpus is the original knowledge pipeline for Azure Databricks documentation and optional internal Azure Databricks wiki / TSG content.

### 1. `01_ingestion.ipynb`

Purpose: build the raw Databricks documentation table.

What it does:

- Creates or verifies Unity Catalog assets:
  - Catalog: `chatbot`
  - Schema: `chatbot.rag_chatbot`
  - Volume: `/Volumes/chatbot/rag_chatbot/raw_docs`
- Reads the Azure Databricks Microsoft Learn TOC:
  - `https://learn.microsoft.com/en-us/azure/databricks/toc.json`
- Normalizes and deduplicates Databricks documentation URLs.
- Scrapes documentation pages in parallel using Spark workers.
- Optionally ingests internal markdown content from:
  - `/Volumes/chatbot/rag_chatbot/raw_docs/internal_wiki/AzureDataBricks.wiki`
- Cleans markdown noise from internal wiki content.
- Combines Microsoft Learn docs and internal wiki docs.
- Writes the final raw corpus to:
  - `chatbot.rag_chatbot.raw_docs`

Why it matters:

This notebook creates the raw source-of-truth table for Databricks retrieval. It supports both official documentation and optional internal field troubleshooting guidance.

### 2. `02_chunk_embed.ipynb`

Purpose: convert raw Databricks docs into embedded retrieval chunks.

Input:

- `chatbot.rag_chatbot.raw_docs`

Output:

- `chatbot.rag_chatbot.doc_chunks`

What it does:

- Reads raw Databricks docs.
- Adds source metadata when older rows do not already have it.
- Splits each document into overlapping chunks.
- Uses approximately 1,000 characters per chunk with 200 characters of overlap.
- Calls the Databricks Foundation Model API through `mlflow.deployments`.
- Embeds each chunk with `databricks-gte-large-en`.
- Writes one row per chunk with an embedding vector.
- Validates total chunk count, null embeddings, and embedding vector length.

Why it matters:

This step turns long documents into semantically searchable retrieval units that are small enough to fit into model prompts and precise enough for source-backed answers.

### 3. `03_vector_search.ipynb`

Purpose: publish Databricks chunks to Mosaic AI Vector Search.

Input:

- `chatbot.rag_chatbot.doc_chunks`

Output index:

- `chatbot.rag_chatbot.doc_chunks_index`

What it does:

- Creates or reuses the Vector Search endpoint:
  - `databricks-expert-endpoint`
- Enables Delta Change Data Feed on `chatbot.rag_chatbot.doc_chunks`.
- Creates a triggered Delta Sync index.
- Uses `chunk_id` as the primary key.
- Uses the precomputed `embedding` column.
- Uses embedding dimension `1024`.
- Polls index status until ready.
- Includes optional sync and status inspection cells.

Why it matters:

This notebook makes the Databricks chunk table available to the app as a low-latency semantic retrieval index.

## Fabric Corpus Pipeline

Location: `Notebooks/fabric Corpus/`

The Fabric corpus keeps Microsoft Fabric documentation separate from Databricks so the app can answer Fabric questions with Fabric evidence.

### 1. `01_ingestion_fabric.py`

Purpose: ingest Microsoft Fabric documentation from Microsoft Learn.

Input sources:

The script reads multiple Fabric workload TOCs because Fabric docs are split by workload family rather than one all-up TOC.

Configured doc families:

- `fundamentals`
- `admin`
- `data_engineering`
- `data_factory`
- `data_science`
- `data_warehouse`
- `real_time_intelligence`
- `onelake`
- `database`
- `mirroring`
- `cicd`
- `security`
- `governance`
- `workload_development_kit`

Output:

- `chatbot.rag_chatbot.raw_docs_fabric`

What it does:

- Creates or verifies the catalog, schema, and volume.
- Fetches and parses each Fabric TOC.
- Normalizes URLs to `learn.microsoft.com/en-us/fabric/...`.
- Deduplicates pages.
- Scrapes page title and main content.
- Computes a SHA-256 content hash.
- Writes successfully scraped pages to the Fabric raw Delta table.
- Validates row counts, duplicate URLs, missing content, schema, and content length distribution.
- Appends rollout metadata to:
  - `chatbot.rag_chatbot.rag_corpus_metadata`
- Appends ingestion metrics to:
  - `chatbot.rag_chatbot.rag_ingestion_metrics`
- Optionally logs scrape errors to:
  - `chatbot.rag_chatbot.rag_ingestion_errors`
- Includes a disabled optional path for building a unified raw table:
  - `chatbot.rag_chatbot.raw_docs_all`

Why it matters:

Fabric has many workload-specific documentation areas. This ingestion script preserves `product`, `doc_family`, `source`, `source_type`, and `toc_url` so the app can retrieve precise Fabric evidence.

### 2. `02_chunk_embed_fabric.py`

Purpose: chunk and embed the Fabric raw corpus.

Input:

- `chatbot.rag_chatbot.raw_docs_fabric`

Output:

- `chatbot.rag_chatbot.doc_chunks_fabric`

What it does:

- Validates required raw table columns: `url`, `title`, and `content`.
- Preserves or normalizes recommended metadata:
  - `product`
  - `doc_family`
  - `source`
  - `source_type`
  - `cloud`
  - `toc_url`
  - `content_hash`
  - `scraped_date`
- Filters out invalid or very short content.
- Splits content into 1,000-character chunks with 200-character overlap.
- Creates deterministic chunk IDs using:
  - `fabric::<url>::chunk::<chunk_index>`
- Tests the embedding endpoint before running the full corpus.
- Embeds chunks with `databricks-gte-large-en` through a pandas UDF.
- Writes the Fabric chunk table.
- Validates null embeddings, duplicate chunk IDs, embedding length, and metadata coverage.
- Appends embedding metrics to:
  - `chatbot.rag_chatbot.rag_embedding_metrics`
- Includes a disabled optional path for building a unified chunk table:
  - `chatbot.rag_chatbot.doc_chunks_all`

Why it matters:

This script keeps Fabric retrieval cleanly separated from Databricks retrieval while preserving workload metadata for better answer quality and future filtering.

### 3. `03_vector_search_fabric.py`

Purpose: publish Fabric chunks to Vector Search.

Input:

- `chatbot.rag_chatbot.doc_chunks_fabric`

Output index:

- `chatbot.rag_chatbot.doc_chunks_fabric_index`

What it does:

- Creates or reuses the shared Vector Search endpoint:
  - `databricks-expert-endpoint`
- Validates that Fabric chunks have required columns, embeddings, unique IDs, and 1,024-dimension vectors.
- Enables Delta Change Data Feed on the Fabric chunk table.
- Creates or reuses a triggered Delta Sync index.
- Runs a manual sync when `RUN_MANUAL_SYNC=true`.
- Waits for index readiness when `WAIT_FOR_READY=true`.
- Describes the index for troubleshooting and auditability.
- Validates the indexed corpus shape by product, doc family, source, and source type.
- Includes a similarity-search smoke test for:
  - `What is Microsoft Fabric OneLake?`
- Appends Vector Search metrics to:
  - `chatbot.rag_chatbot.rag_vector_search_metrics`

Why it matters:

This gives the live app a Fabric-specific semantic retrieval surface, allowing Fabric questions to use Fabric documentation instead of falling back to Databricks-only evidence.

## Power BI Corpus Pipeline

Location: `Notebooks/PBI Corpus/`

The Power BI corpus keeps Power BI, DAX, and Power Query documentation independently retrievable. This matters because Power BI is related to Fabric, but its semantic model, DAX, reporting, gateway, service, and authoring docs have their own concepts and constraints.

### 1. `01_ingestion_powerbi.py`

Purpose: ingest official Microsoft Learn Power BI, DAX, and Power Query documentation.

Configured TOC sources:

- Power BI fundamentals
- Power BI connect data
- Power BI create reports
- Power BI guidance
- DAX
- Power Query

Output:

- `chatbot.rag_chatbot.raw_docs_powerbi`

What it does:

- Uses a `requests.Session` with a configurable user agent.
- Walks each configured TOC recursively.
- Normalizes Microsoft Learn URLs.
- Deduplicates pages across TOCs.
- Scrapes page title and main content using an HTML parser focused on Learn main content.
- Filters out pages below the configured minimum content length.
- Adds metadata such as:
  - `product = powerbi`
  - `doc_family`
  - `source = microsoft_learn`
  - `source_type = official_docs`
  - `cloud = fabric_powerbi`
  - `toc_url`
  - `content_hash`
  - `scraped_date`
- Writes the raw Power BI corpus to Delta.
- Displays doc-family counts and sample rows.

Why it matters:

Power BI retrieval needs its own documentation surface so semantic model, Direct Lake, Import, DirectQuery, DAX, Power Query, gateway, and report-authoring answers do not get diluted by generic Fabric or Databricks context.

### 2. `02_chunk_embed_powerbi.py`

Purpose: chunk and embed the Power BI raw corpus.

Input:

- `chatbot.rag_chatbot.raw_docs_powerbi`

Output:

- `chatbot.rag_chatbot.doc_chunks_powerbi`

What it does:

- Validates required raw table columns: `url`, `title`, and `content`.
- Preserves or normalizes product-aware metadata.
- Filters invalid or very short content.
- Splits content into 1,000-character chunks with 200-character overlap.
- Creates deterministic chunk IDs using:
  - `powerbi::<url>::chunk::<chunk_index>`
- Tests the embedding endpoint before full-corpus embedding.
- Embeds chunks with `databricks-gte-large-en` through a pandas UDF.
- Writes the Power BI chunk table.
- Validates null embeddings, duplicate chunk IDs, embedding length, and metadata coverage.
- Appends embedding metrics to:
  - `chatbot.rag_chatbot.rag_embedding_metrics`
- Includes a disabled optional path for building a unified chunk table:
  - `chatbot.rag_chatbot.doc_chunks_all`

Why it matters:

This creates a Power BI-specific retrieval layer that supports accurate answers about semantic models, DAX, Power Query, report design, service behavior, and Power BI over Fabric patterns.

### 3. `03_vector_search_powerbi.py`

Purpose: publish Power BI chunks to Vector Search.

Input:

- `chatbot.rag_chatbot.doc_chunks_powerbi`

Output index:

- `chatbot.rag_chatbot.doc_chunks_powerbi_index`

What it does:

- Creates or reuses the shared Vector Search endpoint:
  - `databricks-expert-endpoint`
- Validates required columns, embeddings, duplicate IDs, and embedding dimensions.
- Enables Delta Change Data Feed on the Power BI chunk table.
- Creates or reuses a triggered Delta Sync index.
- Runs manual sync when configured.
- Waits for index readiness when configured.
- Describes the index for troubleshooting and auditability.
- Validates indexed corpus shape by product, doc family, source, and source type.
- Includes a similarity-search smoke test for:
  - `What is Power BI OneLake?`
- Appends Vector Search metrics to:
  - `chatbot.rag_chatbot.rag_vector_search_metrics`

Why it matters:

This gives the assistant a dedicated Power BI retrieval index, which is essential for questions involving semantic model mode choices, DAX, Power Query, report authoring, and Power BI service behavior.

## How The App Ties In

The live Fabric-slot app uses the product-separated indexes from this repo.

At runtime, the app:

1. Accepts a user question in the Streamlit UI.
2. Resolves the product route: Databricks, Fabric, Power BI, or Compare / Better Together.
3. Detects topic and intent, such as architecture, troubleshooting, implementation, learning, or customer-ready writing.
4. Selects the matching Vector Search index.
5. Retrieves the most relevant chunks.
6. Builds a structured prompt with retrieved context and topic-specific instructions.
7. Calls the configured Databricks model-serving endpoint.
8. Applies answer repair and deterministic guardrails for high-risk customer-facing topics.
9. Returns a source-backed response with evidence quality and citations.

The product route is what makes the combined app useful. A Power BI semantic model question can retrieve Power BI-specific evidence, a Fabric mirroring question can retrieve Fabric evidence, and a Databricks troubleshooting question can stay grounded in Databricks documentation.

## Product Routing Model

| Route | Retrieval target | Example questions |
| --- | --- | --- |
| Databricks | `doc_chunks_index` | Unity Catalog, ADLS Gen2 access, Spark performance, clusters, model serving, Databricks compliance. |
| Fabric | `doc_chunks_fabric_index` | OneLake, Fabric mirroring, Fabric Lakehouse, Fabric capacity, Fabric workspace governance. |
| Power BI | `doc_chunks_powerbi_index` | Semantic models, Direct Lake, Import, DirectQuery, DAX, Power Query, Power BI reports. |
| Compare / Better Together | Multiple product indexes | Databricks + Fabric + Power BI architecture and customer positioning. |

## Operational Tables

The Fabric and Power BI pipelines also write lightweight observability tables.

| Table | Purpose |
| --- | --- |
| `chatbot.rag_chatbot.rag_corpus_metadata` | Records corpus layer, product, table, rollout status, and notes. |
| `chatbot.rag_chatbot.rag_ingestion_metrics` | Records source counts, target counts, rejected rows, status, and completion time. |
| `chatbot.rag_chatbot.rag_ingestion_errors` | Stores scrape errors when ingestion completes with page-level failures. |
| `chatbot.rag_chatbot.rag_embedding_metrics` | Records chunking and embedding counts, failed embeddings, model, and status. |
| `chatbot.rag_chatbot.rag_vector_search_metrics` | Records Vector Search endpoint, index name, source row count, and sync status. |

## Environment Variables

The notebooks use defaults but can be parameterized with environment variables.

| Variable | Used by | Default / purpose |
| --- | --- | --- |
| `RAG_CATALOG` | Fabric and Power BI scripts | Defaults to `chatbot`. |
| `RAG_SCHEMA` | Fabric and Power BI scripts | Defaults to `rag_chatbot`. |
| `RAG_VOLUME` | Fabric ingestion | Defaults to `raw_docs`. |
| `FABRIC_RAW_TABLE` | Fabric ingestion and chunking | Defaults to `chatbot.rag_chatbot.raw_docs_fabric`. |
| `FABRIC_CHUNKS_TABLE` | Fabric chunking and Vector Search | Defaults to `chatbot.rag_chatbot.doc_chunks_fabric`. |
| `FABRIC_VECTOR_SEARCH_INDEX` | Fabric Vector Search | Defaults to `chatbot.rag_chatbot.doc_chunks_fabric_index`. |
| `POWERBI_RAW_TABLE` | Power BI ingestion and chunking | Defaults to `chatbot.rag_chatbot.raw_docs_powerbi`. |
| `POWERBI_CHUNKS_TABLE` | Power BI chunking and Vector Search | Defaults to `chatbot.rag_chatbot.doc_chunks_powerbi`. |
| `POWERBI_VECTOR_SEARCH_INDEX` | Power BI Vector Search | Defaults to `chatbot.rag_chatbot.doc_chunks_powerbi_index`. |
| `VECTOR_SEARCH_ENDPOINT` | Fabric and Power BI Vector Search | Defaults to `databricks-expert-endpoint`. |
| `EMBED_MODEL` | Fabric and Power BI chunking/search | Defaults to `databricks-gte-large-en`. |
| `CHUNK_SIZE` | Fabric and Power BI chunking | Defaults to `1000`. |
| `CHUNK_OVERLAP` | Fabric and Power BI chunking | Defaults to `200`. |
| `EMBED_BATCH` | Fabric and Power BI chunking | Defaults to `25`. |
| `EMBEDDING_DIMENSION` | Fabric and Power BI Vector Search | Defaults to `1024`. |
| `VECTOR_SEARCH_PIPELINE_TYPE` | Fabric and Power BI Vector Search | Defaults to `TRIGGERED`. |
| `RUN_MANUAL_SYNC` | Fabric and Power BI Vector Search | Defaults to `true`. |
| `WAIT_FOR_READY` | Fabric and Power BI Vector Search | Defaults to `true`. |
| `BUILD_UNIFIED_RAW_TABLE` | Fabric ingestion | Defaults to `false`; only use after routing is ready. |
| `BUILD_UNIFIED_CHUNKS_TABLE` | Fabric and Power BI chunking | Defaults to `false`; only use after routing is ready. |
| `MAX_PAGES_PER_TOC` | Power BI ingestion | Defaults to `0`, meaning unlimited. Useful for test runs. |
| `MIN_CONTENT_CHARS` | Power BI ingestion | Defaults to `400`. Filters weak pages. |

## Recommended Run Order

Run each corpus independently so failures stay isolated.

### Databricks

1. `Notebooks/Databricks Corpus/01_ingestion.ipynb`
2. `Notebooks/Databricks Corpus/02_chunk_embed.ipynb`
3. `Notebooks/Databricks Corpus/03_vector_search.ipynb`

### Fabric

1. `Notebooks/fabric Corpus/01_ingestion_fabric.py`
2. `Notebooks/fabric Corpus/02_chunk_embed_fabric.py`
3. `Notebooks/fabric Corpus/03_vector_search_fabric.py`

### Power BI

1. `Notebooks/PBI Corpus/01_ingestion_powerbi.py`
2. `Notebooks/PBI Corpus/02_chunk_embed_powerbi.py`
3. `Notebooks/PBI Corpus/03_vector_search_powerbi.py`

## Validation Checklist

After each ingestion run:

- Raw table exists.
- Row count is greater than zero.
- Duplicate URL count is zero.
- Missing content count is zero or explained.
- Product and doc-family metadata are populated.

After each chunk/embed run:

- Chunk table exists.
- Chunk count is greater than raw page count.
- Null embedding count is zero.
- Duplicate `chunk_id` count is zero.
- Embedding length is 1024.
- Product metadata is preserved on every chunk.

After each Vector Search run:

- Delta Change Data Feed is enabled on the chunk table.
- Vector Search endpoint is online.
- Product-specific index exists.
- Index sync completes or reaches expected progress.
- Similarity-search smoke test returns relevant documents.

## Demo Prompts For The Fabric Slot

Use these prompts to show why separate product indexes matter.

### Databricks troubleshooting

```text
A Databricks cluster cannot access ADLS Gen2 with public network access disabled. What should I check first?
```

Shows Databricks-specific retrieval around private endpoints, private DNS, RBAC, and Unity Catalog storage permissions.

### Fabric architecture

```text
How should I explain Microsoft Fabric OneLake and mirroring to a customer who already uses Azure Databricks Unity Catalog?
```

Shows Fabric-specific retrieval and cross-product nuance without pretending Fabric mirroring and OneLake shortcuts are the same thing.

### Power BI semantic model architecture

```text
We have Databricks Unity Catalog source data and need Power BI reports. Compare Direct Lake, Import, DirectQuery, and Composite models. What should we recommend?
```

Shows Power BI-specific retrieval and the difference between Fabric-native Direct Lake patterns, Import refresh patterns, DirectQuery to Databricks SQL, and hybrid approaches.

### Customer-ready compliance response

```text
Draft a customer email: If we enable Databricks Compliance Security Profile in one workspace, does it impact other Azure resource groups, non-Databricks services, or another workspace sharing the same ADLS Gen2 account?
```

Shows customer-safe writing and deterministic guardrails for compliance-sensitive answers.

## Presentation Talk Track

Use this framing when presenting the project:

> I built this as a source-backed field assistant for Databricks, Fabric, and Power BI. The goal is to help Microsoft teams get faster, safer, more consistent guidance across products without blending product boundaries incorrectly.

Then describe the pipeline:

> Each product has its own corpus pipeline. We ingest official documentation, preserve product metadata, chunk and embed the text, and publish it to a product-specific Vector Search index. The app then routes the user question to the right index before generating an answer.

Then describe why it is more than a chatbot:

> The important part is not just that it calls a model. It routes first, retrieves source evidence second, applies topic-specific response rules third, and then generates a field-ready answer. That makes it useful for architecture reviews, troubleshooting, customer prep, and cross-product positioning.

Strong phrase to use:

> The notebooks are the knowledge factory. The Fabric slot is the product experience.

## Current Design Decisions

- Product corpora are intentionally separated into Databricks, Fabric, and Power BI tables and indexes.
- Unified raw and chunk tables are present as optional future paths, but disabled by default.
- Vector Search indexes use Delta Sync over precomputed embeddings.
- Fabric and Power BI scripts preserve product metadata for future filtering, ranking, or unified-index migration.
- The live app should select retrieval targets by product route rather than querying one mixed corpus blindly.

## Why This Matters

The assistant is valuable because Microsoft field work often crosses product boundaries. Databricks, Fabric, and Power BI are connected, but they are not interchangeable. This repo builds the retrieval layer that lets the app respect those boundaries while still helping users reason across them.

The result is a more credible assistant for:

- Databricks troubleshooting and architecture.
- Fabric Lakehouse, OneLake, mirroring, and governance scenarios.
- Power BI semantic model and reporting decisions.
- Better Together guidance across Databricks, Fabric, and Power BI.
- Customer-ready responses that are practical, sourced, and safer to share.