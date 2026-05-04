# Databricks + Fabric RAG Expert Assistant

A source-backed field assistant for Azure Databricks, Microsoft Fabric, and Power BI architecture, troubleshooting, implementation guidance, and customer-ready response generation.

This project turns curated product documentation, field playbooks, and notebook-driven knowledge preparation into a live Streamlit assistant backed by Databricks Vector Search and Databricks model serving. The Fabric slot runs the combined Databricks + Fabric + Power BI experience.

## Executive Summary

The assistant is designed for Microsoft field and technical teams who need fast, reliable, source-grounded guidance across Databricks, Fabric, and Power BI scenarios. It helps users move from scattered documentation to actionable answers for architecture decisions, implementation planning, troubleshooting, competitive positioning, and customer communication.

The key idea is simple:

> Route the question to the right product lens, retrieve relevant source context, apply domain-specific answer rules, then generate a field-ready response.

This is not a generic chatbot. It is a routed, source-backed field assistant with product-aware retrieval, topic-specific response contracts, evaluation coverage, and deterministic guardrails for sensitive customer-facing topics.

## What The App Does

- Answers Azure Databricks, Microsoft Fabric, and Power BI questions using retrieved source context.
- Routes each question to the correct product lens: Databricks, Fabric, Power BI, or Compare / Better Together.
- Supports architecture guidance, troubleshooting runbooks, implementation steps, learning explanations, customer meeting prep, and competitive positioning.
- Uses separate retrieval paths for Databricks, Fabric, and Power BI content.
- Produces source-backed answers with evidence quality indicators.
- Includes customer-safe language handling for compliance-sensitive topics such as Databricks Compliance Security Profile.
- Runs as a Streamlit app deployed to Azure App Service.

## Live App

| App | Purpose | URL |
| --- | --- | --- |
| Fabric slot | Combined Databricks + Fabric + Power BI assistant | `https://dbx-fabric-hbbghpckhgd7dec0.centralus-01.azurewebsites.net/` |

The Fabric slot is the main team-facing demo experience because it exposes the combined Databricks, Fabric, Power BI, and cross-product routing behavior.

## High-Level Architecture

```text
Product docs / field playbooks / curated guidance
  |
  v
Notebook preparation flow
  |
  v
Chunking and embedding
  |
  v
Databricks Vector Search indexes
  |
  v
Streamlit app on Azure App Service
  |
  v
Databricks model serving endpoints
  |
  v
Source-backed field-ready response
```

The architecture has four major layers:

1. **Knowledge preparation**: notebooks and scripts collect, clean, chunk, and embed the content.
2. **Retrieval**: Databricks Vector Search indexes provide semantic search over the prepared chunks.
3. **Reasoning and response generation**: Databricks model serving endpoints generate answers from retrieved context and structured instructions.
4. **Application experience**: Streamlit provides a field-friendly interface with product routing, answer modes, citations, and quality guardrails.

## Runtime Flow

When a user asks a question, the app follows this pattern:

1. Resolve the product route: Databricks, Fabric, Power BI, or Compare.
2. Detect the topic and intent, such as architecture, troubleshooting, implementation, learning, or customer meeting prep.
3. Build a standalone retrieval query from the current question, attachments, and chat history.
4. Retrieve relevant chunks from the appropriate Vector Search index.
5. Assemble a model prompt with retrieved context, topic rules, answer-format rules, and customer-safe writing rules.
6. Call the configured Databricks model serving endpoint.
7. Repair or sanitize the answer when required for high-risk topics.
8. Return a source-backed answer with evidence quality and citations.

The design principle is:

> Route before retrieval. Retrieve before generation. Validate before customer-facing output.

## Notebook Flow

The notebook story has two complementary parts: a Fabric data science workflow and the RAG knowledge pipeline.

### Fabric Lakehouse And ML Notebooks

These notebooks demonstrate the end-to-end Fabric analytical workflow: ingest, explore, prepare, train, and score.

| Notebook | Purpose | What It Demonstrates |
| --- | --- | --- |
| `01-ingest-data-into-fabric-lakehouse-using-apache-spark.ipynb` | Ingest source data into a Fabric Lakehouse | Connects to Azure Open Datasets, reads NYC Taxi yellow cab data, and writes it as a Lakehouse Delta table. |
| `02-explore-and-visualize-data-using-notebooks.ipynb` | Explore and visualize the Lakehouse data | Reads Delta data, samples it for analysis, and visualizes distributions such as trip duration. |
| `03-perform-data-cleansing-and-preparation-using-apache-spark.ipynb` | Clean and prepare the analytical dataset | Loads raw Delta data, computes summary statistics, cleans records, creates derived columns, and writes prepared Delta output. |
| `04-train-and-track-machine-learning-models.ipynb` | Train and track an ML model | Reads prepared data, creates train/test splits, defines feature engineering, trains with Spark ML / SynapseML patterns, and tracks runs with MLflow. |
| `05-perform-batch-scoring-and-save-predictions-to-lakehouse.ipynb` | Run batch scoring and persist predictions | Loads the trained model, scores new data, cleans prediction output, and writes predictions back to the Lakehouse. |

Together these notebooks show a complete Fabric data workflow:

```text
Ingest -> Explore -> Clean/Prepare -> Train/Track -> Batch Score -> Persist Predictions
```

### RAG Preparation Notebooks

These notebooks are the bridge between source material and the live assistant.

| Notebook | Purpose | What It Demonstrates |
| --- | --- | --- |
| `02_chunk_embed.ipynb` | Chunk and embed the source knowledge | Splits documentation and curated guidance into retrievable chunks, generates embeddings, and prepares the data structure for semantic search. |
| `03_vector_search.ipynb` | Create and validate Vector Search retrieval | Creates or updates Databricks Vector Search indexes and validates that semantic retrieval returns useful context for the app. |

The RAG notebooks are the knowledge factory. The Streamlit app is the product experience.

## Vector Search Design

The app is built to support multiple retrieval indexes so that answers stay aligned to the right product domain.

Typical index layout:

| Index | Purpose |
| --- | --- |
| Databricks documentation index | Core Azure Databricks architecture, implementation, troubleshooting, and governance guidance. |
| Fabric documentation index | Microsoft Fabric architecture, lakehouse, mirroring, OneLake, and Fabric integration guidance. |
| Power BI documentation index | Semantic model, Direct Lake, Import, DirectQuery, governance, and report-serving guidance. |

This matters because cross-product assistants can fail when they blend concepts too freely. A Power BI Direct Lake question should not receive a generic Databricks answer, and a Databricks Unity Catalog question should not be answered as if Fabric governance automatically applies.

## Product Routing

The Fabric slot exposes multiple product lenses:

- **Databricks**: Azure Databricks-focused architecture, troubleshooting, Unity Catalog, Spark, model serving, Lakehouse, and security guidance.
- **Fabric**: Microsoft Fabric workspace, Lakehouse, OneLake, mirroring, capacity, and integration guidance.
- **Power BI**: Semantic models, Direct Lake, Import, DirectQuery, Composite models, RLS/OLS, deployment pipelines, and reporting architecture.
- **Compare / Better Together**: Cross-product positioning across Databricks, Fabric, and Power BI.

The app can also run in Databricks-only mode for the production slot and DP-700 certification mode for the SME slot.

## Answer Modes And Use Cases

The assistant is optimized for practical field workflows.

| Use Case | Example |
| --- | --- |
| Architecture guidance | Compare Direct Lake, Import, DirectQuery, and Composite semantic model patterns over Databricks-backed data. |
| Troubleshooting | Diagnose ADLS Gen2 private endpoint access failures from Databricks compute. |
| Implementation planning | Provide step-by-step Fabric mirroring or Databricks Unity Catalog setup guidance. |
| Customer meeting prep | Create a concise customer-ready talk track with risks, validation steps, and next actions. |
| Competitive positioning | Separate valid architecture concerns from competitor framing and produce a field response. |
| Learning | Explain concepts such as Unity Catalog, OneLake, Direct Lake, or Compliance Security Profile in practical terms. |

## Topic-Specific Playbooks

The app includes specialized handling for high-value and high-risk topics, including:

- Microsoft Fabric mirroring and Fabric access to Databricks / Unity Catalog data.
- Power BI semantic model architecture over Fabric and Databricks-backed data.
- ADLS Gen2 private access from Databricks.
- Unity Catalog architecture and setup.
- Spark and notebook performance troubleshooting.
- Databricks cluster startup and bootstrap diagnostics.
- Databricks Compliance Security Profile and compliance architecture.
- Cross-product competitive positioning.

These topic rules help the app avoid generic answers and produce guidance that is useful in real customer and field scenarios.

## Customer-Safe Compliance Guardrails

Compliance and security topics require extra care. For customer-facing CSP responses, the app avoids broad reassurance such as:

- `unaffected`
- `no impact`
- `definitive answers`
- `workspace-isolated`
- blanket claims that other services or resource groups are outside scope

Instead, the app uses safer language such as:

- CSP does not automatically reconfigure other Azure services.
- CSP does not automatically propagate to other workspaces.
- Shared storage, identity, networking, logging, monitoring, and compliance dependencies should still be validated.
- Regulated-data access paths may require equivalent controls as a governance decision.

This guardrail is implemented deterministically after model generation because prompt-only safety is not reliable enough for customer-facing compliance claims.

## Evaluation Harness

The project includes an offline evaluation harness with 50 representative questions across routes, intents, and source expectations.

The eval flow checks:

- Product route detection.
- Intent detection.
- Expected answer structure.
- Source and evidence behavior.
- Coverage across Databricks, Fabric, Power BI, and comparison scenarios.

Latest validated results:

- 50 / 50 cases passed.
- Route accuracy: 100%.
- Intent accuracy: 100%.
- Average score: 98.4.

This matters because multi-product assistants need repeatable quality checks. The biggest risk is not just a bad answer; it is a confident answer using the wrong product lens.

## Deployment Model

The app is deployed to Azure App Service with slot-specific configuration.

### Production Slot

Databricks-only route:

```text
ENABLE_FABRIC=false
ENABLE_POWERBI=false
APP_VARIANT=databricks_only
DEFAULT_PRODUCT_ROUTE=Databricks
VISIBLE_PRODUCT_ROUTES=Databricks
```

### Fabric Slot

Combined Databricks + Fabric + Power BI route:

```text
ENABLE_FABRIC=true
ENABLE_POWERBI=true
```

### SME Slot

Personal DP-700 certification assistant:

```text
APP_VARIANT=dp700_cert_personal
DP700_CERT_ONLY=true
ENABLE_FABRIC=false
ENABLE_POWERBI=false
DEFAULT_PRODUCT_ROUTE=DP700
```

## Important Environment Settings

The app expects Databricks and Vector Search configuration through environment variables or App Service settings.

| Setting | Purpose |
| --- | --- |
| `DATABRICKS_HOST` | Databricks workspace host. |
| `DATABRICKS_TOKEN` or OAuth client settings | Authentication for Databricks APIs. |
| `VECTOR_SEARCH_ENDPOINT` | Databricks Vector Search endpoint. |
| `VECTOR_SEARCH_INDEX` | Databricks document index. |
| `FABRIC_VECTOR_SEARCH_INDEX` | Fabric document index. |
| `POWERBI_VECTOR_SEARCH_INDEX` | Power BI document index. |
| `CHAT_MODEL` | General chat model serving endpoint. |
| `REASONING_MODEL` | Higher-reasoning model endpoint for architecture and complex topics. |
| `SCREENSHOT_MODEL` | Optional multimodal / screenshot extraction endpoint. |
| `EMBED_MODEL` or `EMBEDDING_MODEL` | Embedding model name. |
| `ENABLE_FABRIC` | Enables Fabric route and Fabric index. |
| `ENABLE_POWERBI` | Enables Power BI route and Power BI index. |
| `APP_VARIANT` | Controls slot-specific behavior. |

## Deployment Commands

Typical deployment flow:

```powershell
Set-Location C:\Users\edcolby\Downloads
c:/Repos/Cursor/.venv/Scripts/python.exe -m py_compile .\appservice.py

$zip = "dbx-fabric-release-$(New-Guid).zip"
Compress-Archive -Path .\appservice.py, .\requirements.txt -DestinationPath $zip -Force

az webapp deploy `
  --resource-group appservice `
  --name DBX `
  --slot fabric `
  --src-path $zip `
  --type zip `
  --clean true `
  --restart true

az webapp restart --resource-group appservice --name DBX --slot fabric
```

Health check:

```powershell
Invoke-WebRequest `
  -Uri 'https://dbx-fabric-hbbghpckhgd7dec0.centralus-01.azurewebsites.net/_stcore/health' `
  -UseBasicParsing
```

## Demo Flow

Use the Fabric slot for the primary team demo.

### Demo 1: Fabric And Power BI Architecture

Prompt:

```text
We have Databricks Unity Catalog source data and need to serve Power BI reports. Compare Direct Lake, Import, DirectQuery, and Composite models. What should we recommend?
```

What this demonstrates:

- Fabric / Power BI route handling.
- Direct Lake nuance.
- Databricks-backed data pattern awareness.
- Decision-matrix output.
- Cross-product architecture guidance.

### Demo 2: Databricks Troubleshooting

Prompt:

```text
A Databricks cluster cannot access ADLS Gen2 with public network access disabled. What should I check first?
```

What this demonstrates:

- Practical diagnostic flow.
- Separation of private endpoint, private DNS, RBAC, and Unity Catalog permissions.
- Field-ready troubleshooting output.

### Demo 3: Customer-Ready Compliance Email

Prompt:

```text
Draft a customer email: If we enable Databricks Compliance Security Profile in one workspace, does it impact other Azure resource groups, non-Databricks services, or another workspace sharing the same ADLS Gen2 account?
```

What this demonstrates:

- Customer-ready response generation.
- Compliance-safe wording.
- Deterministic guardrails for risky claims.
- Practical validation checklist.

## Presentation Talk Track

Suggested opening:

> I built this as a field enablement assistant for Databricks, Fabric, and Power BI scenarios. The goal is to reduce time spent hunting across docs, improve consistency of customer-facing guidance, and give teams a safer way to prepare architecture recommendations, troubleshooting steps, and competitive positioning.

Suggested architecture explanation:

> The notebooks are the factory and the app is the product experience. The notebooks prepare content by ingesting, cleaning, chunking, embedding, and indexing it. The app then routes the user question, retrieves the right context, applies product-specific rules, and generates a source-backed answer.

Suggested quality explanation:

> I did not want to judge quality by vibes, so I added an eval harness with representative questions across product routes and answer types. That gives us a repeatable way to catch routing or intent regressions.

Suggested closing:

> The big idea is to give Microsoft teams a practical, source-backed assistant that understands the difference between Databricks, Fabric, and Power BI, and can turn that knowledge into usable field guidance quickly and safely.

## Project Roadmap

Potential next steps:

- Add more official Microsoft Learn, Databricks, Fabric, and Power BI sources.
- Automate scheduled re-indexing.
- Add feedback buttons and answer-quality telemetry.
- Add CI/CD checks that run the eval harness before deployment.
- Add Teams or Copilot Studio integration.
- Add role-specific modes for CSA, Specialist, CSAM, SE, and support engineers.
- Expand deterministic validators for security, compliance, and competitive claims.
- Add richer source coverage diagnostics when retrieved evidence is thin.

## Key Design Principles

- **Product-aware routing**: avoid blending Databricks, Fabric, and Power BI concepts incorrectly.
- **Source-backed generation**: answers should be grounded in retrieved evidence.
- **Field-ready structure**: output should be directly useful for real architecture, implementation, and support scenarios.
- **Customer-safe language**: sensitive topics need conservative, validated wording.
- **Repeatable evaluation**: quality should be tested with a corpus, not only manual spot checks.
- **Slot-specific behavior**: the same codebase can support different app experiences through configuration.

## Repository Status

This repository documents the Databricks + Fabric RAG assistant and should evolve into the source home for:

- App source code.
- Notebook pipeline assets.
- Evaluation harness.
- Deployment scripts.
- Architecture diagrams.
- Demo prompts and presentation materials.

Current README content captures the working system design, deployment model, notebook flow, and presentation story for the Fabric slot experience.
