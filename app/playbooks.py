PLAYBOOKS = {
    "adls_private_access": """
# Playbook: Databricks private access to ADLS Gen2 storage account

Use this when the user asks how Azure Databricks can access an ADLS Gen2 storage account that is private-network-only, has public network access disabled, uses private endpoints, or is blocked by storage firewall/private access policy.

Critical distinction:
- Do NOT confuse Databricks workspace private endpoints with storage account private endpoints.
- Databricks private endpoint subresources such as databricks_ui_api and browser_auth are for private access into the Databricks workspace UI/API.
- They are NOT used to let Databricks compute access ADLS Gen2.
- For ADLS Gen2 private access, the private endpoint is created on the storage account, usually for the dfs subresource and often also blob.

Correct mental model:
- Private endpoint + private DNS = network path.
- Access Connector managed identity + Azure RBAC = storage identity permission.
- Unity Catalog storage credential + external location + grants = Databricks governance.

Architecture:
- Databricks compute can be in Dbx-Pub / Dbx-Priv delegated subnets.
- Storage private endpoints should be in a separate non-delegated subnet in the same VNet or a peered/routable VNet.
- Private endpoints cannot be created in Databricks delegated subnets.
- Same VNet subnets can normally route to each other unless NSGs/UDRs/firewalls block traffic.

Storage private endpoint setup:
1. Create a private endpoint on the storage account for dfs.
2. Usually also create a private endpoint on the storage account for blob.
3. Put the private endpoints in a dedicated subnet such as PrivateEndpoints or StoragePrivateEndpoints.
4. Do not use Dbx-Pub or Dbx-Priv for private endpoints because those subnets are delegated to Databricks.
5. Ensure private DNS zones exist:
   - privatelink.dfs.core.windows.net
   - privatelink.blob.core.windows.net
6. Link those private DNS zones to the VNet used by Databricks compute.
7. Confirm each DNS zone has an A record for the storage account pointing to the private endpoint IP.

How Databricks uses the private endpoint:
- Databricks does not use a special privatelink URL in code.
- Databricks still uses the normal ADLS Gen2 URL:
  abfss://<container>@<storage-account>.dfs.core.windows.net/<path>
- DNS resolves <storage-account>.dfs.core.windows.net to:
  <storage-account>.privatelink.dfs.core.windows.net
  and then to a private IP such as 10.x.x.x.
- If public network access is disabled, only clients that can resolve and reach that private IP can access the storage account.

Validation from Databricks:
1. Run DNS check:
   nslookup <storage-account>.dfs.core.windows.net
2. Expected result:
   <storage-account>.privatelink.dfs.core.windows.net
   Address: 10.x.x.x
3. If it resolves to a public IP, private DNS is not wired correctly to the Databricks VNet.
4. Test file access:
   dbutils.fs.ls("abfss://<container>@<storage-account>.dfs.core.windows.net/")
5. If DNS resolves privately but access fails, troubleshoot identity/RBAC/Unity Catalog grants.

Identity and permissions:
- Use a Databricks Access Connector managed identity for Unity Catalog.
- Grant the managed identity Storage Blob Data Contributor on the storage account or container for Delta read/write.
- For read-only, Storage Blob Data Reader may be enough.
- Create a Unity Catalog storage credential backed by the Access Connector.
- Create a Unity Catalog external location pointing to:
  abfss://<container>@<storage-account>.dfs.core.windows.net/<folder>
- Grant READ FILES and WRITE FILES on the external location as needed.
- Also grant USE CATALOG, USE SCHEMA, CREATE TABLE, SELECT, MODIFY depending on table operations.

Common mistakes:
- Creating a Databricks workspace private endpoint instead of a storage account private endpoint.
- Choosing databricks_ui_api or browser_auth when the real goal is ADLS access.
- Trying to create a private endpoint in Dbx-Pub or Dbx-Priv delegated subnets.
- Using the privatelink DNS name directly in abfss paths.
- Forgetting the dfs private endpoint.
- Forgetting the blob private endpoint when libraries/tools require blob APIs.
- Forgetting private DNS zone links to the Databricks VNet.
- DNS resolving to a public IP after public access is disabled.
- Assuming private endpoint solves permissions. It only solves network path.
- Missing Storage Blob Data Contributor on the Access Connector managed identity.
- Missing Unity Catalog external location grants.

If the user asks "how does it work":
- Explain that the storage account gets a private IP inside the VNet.
- Clients still use the normal storage hostname.
- Private DNS maps the normal hostname to the private endpoint IP.
- If public access is disabled, only clients with DNS/routing to that private IP can connect.
""",
    "fabric_mirroring": """
# Playbook: Microsoft Fabric mirroring / Fabric access from Azure Databricks Unity Catalog

Use this when the user asks about Microsoft Fabric mirroring or reading Azure Databricks Unity Catalog data from Fabric.

Critical distinction:
- This is primarily a Microsoft Fabric configuration workflow.
- Do not treat it as a generic Databricks external location, storage credential, or external table setup.
- Do not present OneLake shortcuts as the same thing as Fabric mirroring. If retrieved context only supports shortcut-based access, say that clearly and label it as "Fabric shortcut/read access", not mirrored database replication.
- Start with a decision gate: confirm whether the customer wants Fabric mirrored database / mirroring behavior, or simply Fabric read access to Databricks/Unity Catalog data.
- If the user says Databricks and Unity Catalog are already set up, do not include metastore, workspace assignment, catalog creation, or schema creation steps.

Databricks-side prerequisites:
- Azure Databricks workspace exists.
- Unity Catalog is enabled.
- Source catalog/schema/tables exist.
- The identity configuring Fabric access has required Unity Catalog privileges.
- For Fabric reading registered UC data, check whether EXTERNAL USE SCHEMA is required on the UC schema.
- Confirm whether source tables are supported for Fabric access/mirroring.
- Confirm whether UC row filters, column masks, and other policies are enforced downstream in Fabric. Do not assume they are.
- Confirm whether source tables are Delta tables, views, materialized views, streaming tables, or secured tables; unsupported object types should be identified before implementation.
- Confirm whether private networking/firewall restrictions allow Fabric to reach the source/metadata path.

Fabric-side conceptual flow:
1. Confirm Fabric capacity, workspace permissions, and tenant/region feature availability.
2. In Fabric, choose the specific supported experience: mirrored database / mirroring if available, or OneLake shortcut/read access if that is the documented supported path.
3. Create the Fabric connection to Azure Databricks / Unity Catalog using the supported identity method.
4. Select the Databricks workspace, Unity Catalog catalog, schema, and eligible Delta tables.
5. Start the mirror/read-access setup and monitor initial sync or metadata scan status.
6. Validate from Fabric using the lakehouse, SQL analytics endpoint, semantic model, or shortcut target depending on the chosen experience.
7. Validate from Databricks using DESCRIBE DETAIL, SHOW GRANTS, table history/freshness, and source table eligibility checks.

Recommended answer shape for implementation requests:
1. First decision: mirroring vs shortcut/read access
2. Prerequisites and blockers
3. Identity and permissions
4. Fabric-side setup steps
5. Databricks-side validation steps
6. Unsupported scenarios and gotchas
7. Go-live validation checklist
8. Fallback options if the requested path is unsupported

Common gotchas:
- User has Databricks access but lacks required Unity Catalog privileges.
- Fabric connection identity differs from the interactive user.
- UC security policies may not automatically apply to downstream Fabric users.
- Unsupported table types/features.
- Private networking/firewall restrictions between Fabric and Databricks.
- Mirroring feature availability may depend on Fabric region/capacity/tenant settings.
- Assuming shortcuts are replication. Shortcuts provide access/reference semantics; mirroring implies a different replicated/managed experience if supported.
- Assuming Unity Catalog lineage or Databricks policies automatically cover all Fabric-side operations. Validate governance behavior explicitly.
""",
    "powerbi_semantic_architecture": """
# Playbook: Power BI semantic model architecture over Microsoft Fabric and Databricks-backed data

Use this when the user asks about Power BI semantic models, Direct Lake, Import, DirectQuery, Fabric, OneLake, Databricks SQL, mirrored data, shortcuts, governance, performance, cost, or enterprise BI architecture.

Required first principle:
- Do not describe Direct Lake, Import, and DirectQuery as interchangeable connection settings. They imply different data movement, freshness, performance, semantic ownership, capacity, and governance boundaries.
- Do not collapse Databricks-backed data patterns into one option. Separate DirectQuery to Databricks SQL, Import from Databricks, Fabric mirrored/replicated data if supported, OneLake shortcut/read access, and Direct Lake over Fabric-managed Delta data.
- For Databricks Unity Catalog source data, do not make a blanket recommendation to use Direct Lake. The production recommendation should be conditional: use DirectQuery to Databricks SQL when source freshness/source governance is primary, Import when report performance and controlled refresh are primary, and Direct Lake only when the data is available as supported Fabric/OneLake Delta data and the Direct Lake constraints are validated.

Decision model:
- Direct Lake: best candidate when the semantic model can read supported OneLake/Delta data with Fabric capacity, table support, fallback behavior, security, and modeling limitations validated. It avoids traditional import refresh, but it is not a blanket replacement for Import or DirectQuery.
- Direct Lake should not be described as directly connecting to Unity Catalog tables. For Databricks-origin data, first identify how the data becomes available in Fabric/OneLake, such as a supported mirror, shortcut/read-access pattern, pipeline/copy, or other documented integration. Then evaluate Direct Lake over the Fabric-managed/accessible Delta data if supported.
- Import: best candidate when business users need consistently fast interactive reports, the dataset can tolerate refresh latency, and the team accepts a Power BI-managed cache/copy with separate refresh, security, certification, and lifecycle governance.
- DirectQuery: best candidate when source freshness or source-governed access matters more than raw report speed. Validate Databricks SQL warehouse sizing, query folding/translation, gateway/networking if applicable, semantic model limitations, RLS/security behavior, concurrency, and cost.
- Composite/hybrid: use when hot/aggregate data can be imported or Direct Lake while detail or regulated slices stay live. Validate model complexity and user experience carefully.

Governance boundary:
- Unity Catalog governs Databricks assets and access to Databricks-backed data at the source.
- Fabric workspace, item permissions, OneLake permissions, semantic model permissions, endorsement/certification, deployment pipelines, RLS/OLS, and report sharing are separate governance layers.
- If data is imported, cached, mirrored, or materialized in Fabric/Power BI, validate where security policies are enforced after the movement or cache is created.
- Do not claim UC masks, row filters, tags, lineage, or grants automatically govern every downstream Power BI report or Fabric artifact.

Architecture answer requirements:
1. Give a direct recommendation first.
2. Include a decision matrix with rows for Direct Lake, Import, DirectQuery, and optionally Composite/Hybrid.
3. Include a recommended reference pattern for Databricks-backed data.
4. Include a governance/security boundary section.
5. Include performance/cost tradeoffs tied to Fabric capacity, Power BI semantic model refresh/cache behavior, Databricks SQL warehouse cost/performance, and concurrency.
6. Include a proof-of-concept checklist with validation tests before committing to the customer.

Validation checklist:
- Confirm source data location: Databricks Delta/UC, OneLake lakehouse/warehouse, mirrored database, shortcut, or imported copy.
- Confirm required freshness and acceptable latency.
- Confirm report concurrency, expected audience size, query complexity, and peak usage.
- Confirm RLS/OLS/security enforcement location.
- Confirm semantic model ownership, certification, deployment pipeline, and change-management process.
- Test representative DAX queries and visuals with expected data volume.
- Test fallback behavior, refresh failures, query folding/source pushdown, and capacity/warehouse utilization.
- Confirm audit/lineage expectations and who owns incidents.
""",
    "cluster_bootstrap": """
# Playbook: Azure Databricks cluster bootstrap/startup failure

Use this when the user says a cluster fails to start, gets stuck pending, has bootstrap errors, init script failures, driver/worker creation problems, or fails after a few minutes.

Do not give generic Spark tuning advice.

Immediate triage:
1. Compute > failed cluster > Event log.
2. Capture the first red error entry and timestamp.
3. Check whether driver was created.
4. Check driver logs if available.
5. Check worker logs if workers were created.
6. Check init script stdout/stderr if init scripts exist.
7. Check Libraries tab / library install events.
8. Check cluster policy, access mode, node type, instance pool, and runtime.

Most common causes:
1. Init script failure.
2. Library install failure during startup.
3. Network egress issue to package/artifact repositories.
4. DNS/firewall/NAT/NSG/UDR issue.
5. Azure quota, capacity, subnet capacity, or VM SKU issue.
6. Instance pool problem.
7. Cluster policy/access mode mismatch.
8. Workspace/storage/private endpoint restrictions.
9. Custom Spark config/environment variable issue.
""",
    "compliance_architecture": """
# Playbook: Databricks Compliance Security Profile architecture / compliance boundary

Use for CSP, HIPAA, regulated data, shared storage, downstream impact, and Azure compliance questions.

Key principles:
- CSP is a Databricks workspace-level security/compliance setting.
- Do not imply CSP automatically propagates to other workspaces, storage accounts, Azure resource groups, Unity Catalog metastores, or non-Databricks services.
- Distinguish platform enforcement boundary from customer compliance boundary.
- If multiple workspaces access the same regulated data, customer may need equivalent controls as a governance/compliance decision.
- Treat meeting notes or customer-provided claims as unverified unless official retrieved docs confirm them.
""",
    "unity_catalog_setup": """
# Playbook: First-time Unity Catalog setup on Azure Databricks

Use when user asks for hand-holding, from scratch, first setup, enable UC, create metastore.

Azure prerequisites:
- Azure Databricks workspace.
- ADLS Gen2 storage account with hierarchical namespace enabled.
- Storage container for metastore root storage.
- Azure Databricks Access Connector.
- Storage Blob Data Contributor assigned to Access Connector managed identity.

Account-level steps:
- Open Databricks Account Console.
- Create metastore.
- Set region.
- Set metastore storage root path.
- Assign workspace to metastore.
- Assign metastore admins.

Workspace-level steps:
- Verify workspace has metastore.
- Create catalog.
- Create schema.
- Grant USE CATALOG, USE SCHEMA, CREATE TABLE, SELECT, MODIFY as needed.
- Create test table.
""",
    "uc_external_storage": """
# Playbook: Unity Catalog external storage / ADLS permission errors

Use when user mentions external location, storage credential, ABFSS, READ FILES, WRITE FILES, another storage account.

Separate two permission layers:
1. Azure RBAC on storage account/container for the Access Connector managed identity.
2. Unity Catalog grants on storage credential/external location.

Common UC grants:
- GRANT READ FILES ON EXTERNAL LOCATION <external_location_name> TO `<principal_name>`;
- GRANT WRITE FILES ON EXTERNAL LOCATION <external_location_name> TO `<principal_name>`;

Do not grant permissions directly to an abfss URL.
Do not say "storage location" when UC object is "external location".
""",
    "spark_performance": """
# Playbook: Spark performance troubleshooting

Use when user asks about slow Spark jobs, skew, shuffle, spill, performance regression.

Do not jump to AQE/Photon/repartition/caching before diagnosis.

First compare known-good vs bad run:
- input rows/bytes
- files count and file size
- cluster size/node type
- DBR version
- Photon on/off
- code changes
- data layout changes

Spark UI checks:
- longest stage
- task duration variance/skew
- shuffle read/write
- spill memory/disk
- task retries
- executor loss
- driver/executor CPU/memory
""",
}

