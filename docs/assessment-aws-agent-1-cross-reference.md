# Assessment: `aws_agent_1` cross-referenced against the AWS data engineering landscape

**Date:** 2026-08-25
**Subject repo:** `/Users/paulsnyman/Code/aws_agent_1` (HEAD `97e759e`, last commit 2026-07-19, clean tree)
**Reference:** [`aws-data-engineering-landscape.md`](./aws-data-engineering-landscape.md)

**Revised 2026-08-26 (HEAD `b82c35f`).** The AgentCore Gateway finding was wrong and is
corrected throughout: the repo does build a Gateway, with a Lambda target, and calls it
over MCP. The cause was a search pathspec that omitted `.ts`, which is where the CDK stack
lives. See [2.1](#21-evidence-for-the-absence-claim) and [2.2](#22-agentcore-surface-repo-vs-the-current-13-services).
Sections 4.4, 6 and 7 are revised on the corrected reading.

All findings below are `[P]`: read from repo bytes or from a command run against the repo
in this session. Commands that produced counts are quoted so they can be re-run.

---

## 1. What the repo actually is

A 100-level (L1 to L100, plus L97b) progressive lab on the **AWS Strands Agents SDK and
the Bedrock AgentCore platform**, built Dec 2025 to Jul 2026, with an unusually strict
evidence regime:

- Anti-simulation gate (`tools/no_sim_check.py`) flagging stub/fake/mock vocabulary,
  fake-success returns and assume-good `except` defaults
- Statistical rigour on eval claims (Wilson CIs, permutation significance) in
  `tools/eval_harness.py`, terminating in a single GO/NO-GO `tools/ship_gate.py`
- Cross-model validation as a gate: findings are labelled framework-inherent or
  model-specific after a second-provider re-run (Bedrock Haiku, Bedrock Nova Lite)
- ~900-entry append-only `observations.jsonl` plus per-level reflections
- A pre-commit tripwire (`check_no_aws_ids.py`) blocking AWS account identifiers from
  tracked files

Dependency spine (`pyproject.toml`): `strands-agents[otel,a2a,cedar]>=1.48`,
`strands-agents-evals>=0.1.14`, `bedrock-agentcore>=1.12`, `strands-shell>=0.3.1`,
`temporalio`, `ag-ui-*`, `chromadb`, `lancedb`, `graphiti-core[falkordb]`.

This is a **control-plane and runtime** repo. The question is how it lines up with the
data plane described in the landscape doc.

---

## 2. Coverage map

```mermaid
flowchart TB
    subgraph COV["Covered in depth by aws_agent_1"]
        C1["AgentCore Runtime · Memory · Identity<br/>Code Interpreter · Browser · Registry<br/>Payments · Evaluations · Policy/Cedar · AG-UI"]
        C2["MCP: integration (L09) · secure architecture (L56)<br/>elicitation (L60) · toxic flow analysis (L50)"]
        C3["A2A protocol (L32)"]
        C4["Skills as progressive disclosure (L30)"]
        C5["Trajectory + goal-success evals, statistical rigour<br/>(L83 to L86, L91, L92)"]
        C6["Agentic memory, durable resume, red-team (L78 to L99)"]
    end
    subgraph THIN["Touched once, or built without real substance behind it"]
        T1["S3 Vectors (L45, agentic RAG)"]
        T2["Kinesis Data Streams (L37, AgentCore LTM stream delivery)"]
        T3["AgentCore Gateway: wired and deployed (L27 CDK<br/>+ Lambda target + JWT + MCP client, L33 Cedar,<br/>L75 boto3 provision) but the tool behind it is<br/>a no-op placeholder and no call through it is on record"]
    end
    subgraph GAP["Absent"]
        G1["Glue · Glue Data Catalog · Glue 6.0"]
        G2["Athena · Redshift · EMR · Lake Formation"]
        G3["S3 Tables · Apache Iceberg · lakehouse"]
        G4["SageMaker Unified Studio · SageMaker Catalog"]
        G5["Agent Toolkit for AWS · managed AWS MCP Server"]
        G6["AgentCore Harness · Optimization"]
    end
    COV --> THIN --> GAP
```

### 2.1 Evidence for the absence claim

Absence is the highest-risk kind of claim, so it was proved with a broad search over all
tracked text, not a narrow one. Original command:

```
git grep -ril "<term>" -- '*.md' '*.py' '*.json' '*.yaml' '*.toml'
```

**That pathspec was not broad enough, and it is what produced the wrong Gateway finding
below.** It omits `.ts`, and the repo tracks 8 TypeScript files, including
`10_production/l27agentcore/cdk/lib/stacks/agentcore-stack.ts`, which is where L27's
infrastructure actually lives. Enumerating the tracked extensions first would have caught
it:

```
git ls-files | sed 's/.*\.//' | sort | uniq -c | sort -rn
    278 py · 224 md · 29 json · 25 jsonl · 9 sh · 8 ts · 5 gitignore · 4 txt · 3 txn
    3 toml · 3 manifest · 2 yaml · 2 lock · 2 lance · 1 yml
```

The rule this cost: a pathspec is itself a claim about where the answer could be. Drop the
filter entirely, or justify each extension you exclude. Re-run with no filter:

```
git grep -ril "<term>"
```

The data-plane rows below were re-checked that way on 2026-08-26 and all hold. Note that
both research documents now live in this repo, so every term matches them; the counts in
the table are hits **outside** `docs/aws-data-engineering-landscape.md`, this file, and
`NEXT_STEPS_PLAN.md`, which cites both.

| Term | Files | What the hits actually are |
|---|---:|---|
| `s3 tables`, `iceberg`, `lake formation`, `lakeformation`, `data catalog`, `lakehouse`, `datazone`, `sagemaker unified`, `quicksight`, `firehose`, `duckdb` | **0 each** | genuinely absent |
| `athena` | 1 | `observations.jsonl`, and it is an account-separation note ("the data-only sandbox account, meant for Athena/S3 only, nothing agentic"), not data work |
| `redshift` | 1 | the CDK feature flag `@aws-cdk/aws-redshift:columnId` in `10_production/l27agentcore/cdk/cdk.json` |
| `glue` | 2 | both are "Strands powers Amazon Q, Kiro, **AWS Glue** agents", a provenance claim about Strands, not work against Glue |
| `emr` | 1 | the CDK feature flag `@aws-cdk/aws-stepfunctions-tasks:enableEmrServicePolicyV2` |
| `parquet` | 1 | incidental, in `05_advanced/rag_lancedb.py` |
| `msk` | 2 | incidental, both inside `package-lock.json` files |
| `etl` | 7 | all metaphorical ("revisit when building any pipeline ... ETL"), in the L31, L46 and L77 reflections and three incidental files |
| `kinesis` | 15 | real, but all L37: streaming **AgentCore memory events** to a Kinesis Data Stream, plus its `_sandbox` probes |
| `agent toolkit`, `agent-toolkit` | 1 | `docs/levels/L43-...md`, a source link repaired on 2026-08-26 after the `aws-mcp` doc set was rebranded. Registered as a name; still no practice against it |

So: two genuine data-plane touches in 100 levels (L45 S3 Vectors, L37 Kinesis), and both
are agent-infrastructure uses of a data service rather than data engineering.

### 2.2 AgentCore surface, repo vs the current 13 services

Landscape doc section 6.4 lists Harness, Runtime, Memory, Gateway, Identity, Code
Interpreter, Browser, Observability, Payments, Evaluations, Optimization, Policy,
Registry.

| Service | Repo status |
|---|---|
| Runtime | L10, L27 (`BedrockAgentCoreApp`, deployment) |
| Memory | L66 (async LTM filter), L37 (stream delivery), L80, L97/L97b (native vs hand-built rematch) |
| Identity | L74 (workload identity, vaulted secrets) |
| Code Interpreter | L72 |
| Browser | L73 |
| Observability | L21, L34, OTel deps present |
| Payments | L69 (x402) |
| Evaluations | L34, L35, L91 |
| Policy | L33 (Cedar at the Gateway), L96 (Cedar in-process, unified interventions), L99 (deny-policy defends the memory channel) |
| Registry | L71 |
| Config bundles / AG-UI | L75, L44, L76 |
| **Gateway** | **Built, in three places.** L27 provisions one in CDK with a Lambda target and calls it over MCP; L33 attaches Cedar policy to it; L75 creates one through boto3 as a config-bundle target. No dedicated level, and the tool behind the target is a no-op. See 2.3. |
| **Harness** | **No level.** Registered in `LEARNING_PLAN_v148_impact.md` as "AgentCore Harness announced GA at Summit NY 2026 ... SDK surface unverified" |
| **Optimization** | **Absent** (newer than the repo's last delta pass) |

### 2.3 Correction: the Gateway finding, and what is actually missing

The first version of this document said Gateway was "never built against". That was wrong,
and it was wrong because of the pathspec in 2.1.

```mermaid
flowchart LR
    W["'Never built against'<br/>the original finding"]:::wrong

    D1["DECLARED IN IaC<br/>agentcore-stack.ts:76 CfnGateway<br/>:94 CfnGatewayTarget onto a Lambda<br/>config_bundles.py:132 create_gateway"]:::ok
    D2["DEPLOYED<br/>observations.jsonl:815 names<br/>l27agentcore-AgentCoreStack<br/>L33 pins a live gateway id"]:::ok
    D3["DEMONSTRATED<br/>a call landing on a real tool"]:::gap

    W -->|"refuted"| D1
    D1 --> D2
    D2 -.->|"NO record found in the log,<br/>97 reflections or docs/levels/.<br/>level-33-reflection.md:61 says the<br/>gateway had no registered tool schema"| D3

    P["handler.py serves placeholder_tool,<br/>a no-op echoing its arguments"]:::gap
    P -.-> D3

    classDef wrong fill:#5a1e1e,stroke:#8b2c2c,color:#fff
    classDef ok fill:#1b4332,stroke:#2d6a4f,color:#fff
    classDef gap fill:#5c4813,stroke:#8a6d1c,color:#fff
```

Three claims, not one. The original finding denied the first tier; the first correction
of it asserted the third. Both were wrong, and only the middle two are evidenced. The
bytes:

**L27 builds the full path.** `10_production/l27agentcore/cdk/lib/stacks/agentcore-stack.ts`:

```typescript
this.agentCoreGateway = new bedrockagentcore.CfnGateway(this, `${props.appName}-AgentCoreGateway`, {
    name: `${props.appName}-Gateway`,
    protocolType: "MCP",
    roleArn: agentCoreGatewayRole.roleArn,
    authorizerType: "CUSTOM_JWT",          // Cognito discovery URL + allowedClients
```

followed at line 94 by `new bedrockagentcore.CfnGatewayTarget(...)` with
`credentialProviderType: "GATEWAY_IAM_ROLE"` and a `targetConfiguration.mcp.lambda`
carrying an inline `toolSchema`. So the Lambda-to-MCP-tool conversion the landscape doc
credits Gateway with is declared here in IaC. The gateway URL is exported to the runtime
(`"GATEWAY_URL": this.agentCoreGateway.attrGatewayUrl`) and consumed by
`src/mcp_client/client.py`, which fetches a Cognito client-credentials token and returns
`MCPClient(lambda: streamablehttp_client(gateway_url, headers={"Authorization": f"Bearer {access_token}"}))`.

**The stack was deployed.** `observations.jsonl:815` names `l27agentcore-AgentCoreStack`
as a real CloudFormation stack when inventorying the account for migration, and L33 found
the gateway `READY` with `MCP/CUSTOM_JWT`, matching the CDK's own `protocolType` and
`authorizerType`.

**But no tool call through it is on record, and one line says there was no tool to call.**
`.claude/learnings/reflections/level-33-reflection.md:61`:

> **NL2Cedar returns empty findings** the gateway has no registered tool schema, so
> NL2Cedar has nothing to map the natural language onto. Works in production with
> registered MCP tools; falls back to hand-written Cedar here.

Searching `observations.jsonl`, the reflections and `docs/levels/` turns up no record of a
completed MCP call through the Gateway. So the honest reading is: **wired in code and
deployed, never demonstrated end to end.** That is stronger than "never built against",
which was the original error, and weaker than a working integration.

**L33 attaches Cedar to that same gateway.** `11_platform/agentcore_policy.py:62` pins
`GATEWAY_ID = "l27agentcore-gateway-hr4f5b0f6x"`. So the L33 versus L96 comparison is
grounded on a live Gateway, with the caveat above: policy was enforced on a gateway that
had no tools registered, which is also why L33 fell back to hand-written Cedar.

**L75 provisions one through boto3.** `18_agentcore_config/config_bundles.py:132`:

```python
g = control.create_gateway(name=GATEWAY_NAME, roleArn=role_arn,
                           authorizerType="AWS_IAM", protocolType="MCP")
```

with `wait_gateway_ready(gid)` after it and `delete_gateway` in the teardown at line 120.

**What is genuinely missing is the substance behind the target, not the mechanism.** The
Lambda is `10_production/l27agentcore/mcp/lambda/handler.py`, and its one tool is
`placeholder_tool`, whose docstring reads "no-op placeholder tool. Demonstrates argument
passing from AgentCore Gateway" and which returns
`{"message": "Placeholder tool executed.", ...}` plus an echo of the event arguments. It
parses the real `bedrockAgentCoreToolName` header and the wiring around it is genuine, but
no API, database or data service sits behind it.

So the corrected gap is two steps, not a new platform primitive to learn: swap the
placeholder for a real backend, then prove a tool call actually completes through the
Gateway, which nothing in the repo currently shows. That second step is exactly the kind
of claim the repo's own anti-simulation standard exists to force, and it is unproven on
its own Gateway. This moves Gateway out of section 4's gap list and changes
recommendation 7.2 below.

---

## 3. What transfers directly, and is genuinely ahead

Four things in this repo are the correct prerequisites for the agentic data stack, not
merely adjacent to it.

**3.1 The MCP security spine.** L09 (integration), L56 (secure MCP architecture), L60
(elicitation) and L50 (toxic flow analysis, unsafe data paths) are exactly the lens the
landscape doc's three MCP tiers require. Landscape section 6.2 documents AWS's own
default-deny posture (read-only default, `--allow-write` gating, creator-only mutation,
single-statement query enforcement). The repo already reasons in that idiom.

**3.2 Skills as an architecture, not a prompt trick.** L30 built progressive disclosure
by hand: XML menu of names and descriptions, agent activates by name, full instructions
injected on activation, skill stays active for the session. AWS has since shipped that
same shape twice over, as Agent Toolkit agent skills (loaded on demand so they "do not
consume unnecessary context") and as preview **skill assets in Glue Data Catalog**, which
make the pattern catalog-native. L30 is the mechanism layer under both.

**3.3 Trajectory-level evaluation.** L83 (tool selection, ordering, argument
correctness), L84 (multi-turn goal success against real state), L85 (Wilson CIs,
permutation significance). A data agent's failure mode is almost entirely trajectory:
wrong catalog, wrong table, wrong join path, unfiltered scan. This is the single most
transferable asset in the repo, and the data plane makes it *easier* to ground because
ground truth is a checkable row count rather than a judge's opinion.

**3.4 The first-party-ization thesis, already written.** From
`SESSION_2026-07-19-reflection.md`:

> The delta shipped SDK-native versions of five things this repo hand-built (memory,
> interventions, sandbox, storage, agentic context management), turning the hand-built
> levels into the mechanism layer under the new primitives.

The landscape doc is the next chapter of that same thesis on a different axis. What AWS
absorbed between June and August 2026 is **skills** (Agent Toolkit, Glue skill assets),
**context** (AWS Context knowledge graph, Glue business context and semantic search,
S3 Annotations) and **the MCP client wiring itself** (managed AWS MCP Server replacing
per-service self-hosted servers). The thesis holds; the axis moved from runtime to data.

---

## 4. Gaps, ordered by consequence

**4.1 The whole data plane.** Nothing in the repo touches a catalog, a table format, or a
query engine. Every agent in it reasons over documents, memory records, or synthetic
tasks. The landscape doc's entire storage, engine and governance layers are unexercised.

**4.2 No AWS MCP server has ever been wired.** `.mcp.json` contains exactly one server:

```json
{ "mcpServers": { "graphiti-memory": { "command": "npx", "args": ["-y", "mcp-remote", "http://localhost:8000/mcp/"] } } }
```

L09 and L56 built MCP understanding against local and third-party servers. Per 2.3, L27
does call an AWS-hosted MCP endpoint, but it is one the repo stood up itself and filled
with a placeholder tool. None of the AWS-**published** servers has been run: not the
managed AWS MCP Server, not `awslabs/mcp`, not the Knowledge MCP server. So the repo has
MCP mechanism and no AWS MCP practice.

**4.3 Agent Toolkit for AWS is barely registered.** One hit across tracked files, a source
link in `docs/levels/L43-...md` repaired on 2026-08-26 after the `aws-mcp` doc set was
rebranded (section 5). No code, no plugin, no skill. That is thin for something that went
GA in May 2026, before the repo's own July delta pass. It matters because the Toolkit's
`aws-data-analytics` plugin is the exact bridge between this repo and data engineering
work, and because its skills encode AWS's own opinionated defaults, including "Default to
S3 Tables unless the environment says otherwise".

**4.4 The Gateway is wired, deployed, and never demonstrated.** Corrected from the first
version of this document; the evidence is in 2.3. Gateway converts APIs, Lambda functions
and existing services into MCP tools, and it is where AgentCore Policy intercepts every
tool call, so it is the primitive that matters most for data work. L27 wires all of it and
the stack was deployed, but the Lambda behind the target is `placeholder_tool`, a no-op
that echoes its arguments, and no completed call through the Gateway appears anywhere in
the observation log, the reflections or the level docs. L33 says outright that the gateway
had no registered tool schema. The gap is one substitution plus one proof, not one
primitive.

The missing platform primitives are **Harness** and **Optimization**, and neither is on
this axis. Harness is the newer managed agent loop, explicitly aimed at "code generation,
data analysis, and deep research"; Optimization postdates the repo's last delta pass.

**4.5 The delta discipline has no data axis.** The 2026-07-18 ecosystem delta report is
rigorous, but scoped to the SDK. It explicitly parks the platform announcements:

> The AWS News Blog Summit New York index [2] (2026-06-17) and Amazon's own framing piece
> [8] name **platform-level additions invisible at the SDK layer of this report**:
> AgentCore **Managed Knowledge Base** ..., **AgentCore Harness GA**, and **AWS Context**.

That is an honest, self-declared blind spot rather than a miss. But it means AWS Context,
which is the single most consequential item for agent-plus-data work, is logged as a name
and never analysed. The landscape doc fills precisely that hole.

---

## 5. Drift found since the last commit (37 days)

| Item | Repo state | Current state |
|---|---|---|
| `docs/levels/L43-...md:53` links to `https://docs.aws.amazon.com/aws-mcp/latest/userguide/agent-sops.html`, marked verified with a checkmark | assumed live | `curl -L` now resolves to `https://docs.aws.amazon.com/agent-toolkit/latest/userguide/` (HTTP 200 at the guide root, the specific page no longer resolves). The whole `aws-mcp` doc set was rebranded to Agent Toolkit for AWS. **Repaired 2026-08-26**: the link now points at the Skills page and carries the rebrand note. |
| Harness "SDK surface unverified" | open question | Now documented as a first-class AgentCore service: managed agent loop, single API call, isolated microVM with filesystem and shell, explicitly aimed at "code generation, **data analysis**, and deep research", and able to load all Agent Toolkit skills "with one line of code" |
| AWS Context "named, not analysed" | placeholder | Still "coming soon", but the design contract is now public: Iceberg-published context, agentic search APIs **and MCP tools**, per-call IAM and Lake Formation inheritance |
| AgentCore service count | 10 to 11 studied | 13 services, with Optimization new |

Data-plane changes in the same window (Glue 6.0 GA on 2026-08-21, trusted identity
propagation in SMUS on 2026-08-19, data profiling and anomaly detection on 2026-08-18,
Spark Connect on EMR on 2026-08-04) would not have been caught by this repo's delta
process at all, because that process watches the SDK feed. That is the structural finding,
not an oversight.

---

## 6. Assessment

**Fit: high, on one axis only.** `aws_agent_1` is a strong control-plane foundation with a
methodology that is better than most production teams'. Against the landscape doc it is
roughly 80 percent of the agent interface layer and 0 percent of the storage, engine and
governance layers. The join between them is thinner than it first looked: the Gateway is
already built and merely points at a placeholder (2.3), so what is genuinely missing at
the seam is the managed AWS MCP Server and catalog-native skills.

**The methodology is the asset, and it transfers cleanly.** Anti-simulation, positive and
negative controls, cross-model labelling, permutation significance, a paid audit-
reproducible ship gate. Data engineering suits these better than the agent work did:
runtime sentinels are natural (a row count, a manifest version, a snapshot id), ground
truth is checkable rather than judged, and negative controls are trivial to construct.

**The main risk is not staleness, it is axis lock-in.** The repo's watch process is
SDK-shaped, so a data-plane wave passes it invisibly. Anything built on top of this work
should add a second watch on the analytics feed (Glue, Athena, S3 Tables, Lake Formation,
SMUS release notes), because that is now where the agent-relevant surface is moving.

**One correction to carry forward.** The repo's framing of Strands as the substrate needs
a peer now. For data work the managed AWS MCP Server plus the `aws-data-analytics` plugin
is the path AWS is steering toward, and it is framework-agnostic by design (Claude Code,
Kiro, Cursor, Codex). Strands remains the right choice for authoring agents; it is no
longer the only or default way to reach AWS data services from an agent.

---

## 7. Recommended bridge, if this work continues

Sequenced so each step reuses machinery that already exists in `aws_agent_1`.

1. **Wire the managed AWS MCP Server and the `aws-data-analytics` plugin**, then run
   L56's secure-MCP lens and L50's toxic-flow analysis over it. Deliverable: which tool
   calls are read-only, where the write boundary sits, what CloudTrail actually records.
   Reuses: L09, L50, L56.
2. **Give L27's Gateway target a real backend, then prove a call completes through it.**
   Revised on the 2.3 correction: this is no longer "build a Gateway level", because the
   Gateway, its Lambda target, the JWT authorizer and the MCP client are all written and
   the stack was deployed. Two steps. First, replace `placeholder_tool` in
   `10_production/l27agentcore/mcp/lambda/handler.py` with a tool that queries something
   real. Second, capture a completed MCP call through the Gateway with a runtime sentinel,
   because L33 recorded the gateway as having no registered tool schema and nothing in the
   repo shows a call landing. Then re-run L96's intervention taxonomy
   (Deny / Guide / Confirm / Transform) at the Gateway rather than in-process. Cheaper than
   it looked, and it extends the L33 versus L96 comparison on infrastructure that is
   already deployed and Cedar-attached.
3. **Rematch L30 against catalog-native skills.** Hand-built skills plugin versus Glue
   Data Catalog skill assets, using the exact L97 / L97b rematch protocol (test the
   abstraction with a fair store before declaring the native version worse). Preview
   feature, so expect gaps and record them as such.
4. **Port the trajectory evaluator (L83) to a data agent.** Trajectory becomes catalog
   chosen, table resolved, join path taken, filters applied before aggregation. Ground
   truth is a known-correct query. This is the highest-value single item.
5. **Extend `ship_gate.py` with a bytes-scanned budget.** Athena and Glue runs are metered
   on data scanned, not just tokens. The gate already handles a token and latency cost
   gate; the analytics skills report "cost and data scanned" per query, so the signal is
   available.
6. **Add the analytics watch.** A second delta feed alongside the SDK one, covering Glue,
   Athena, S3 Tables, Lake Formation and the SMUS release notes page, which is dated,
   granular and machine-readable.

Deferred item worth revisiting first: the `NEXT_STEPS_PLAN.md` follow-on
"Authentic `BedrockKnowledgeBaseStore` memory arm" is now partly overtaken. AWS Context
and Glue business context are the organisation-scale version of that question, and S3
Annotations plus S3 Metadata give a cheaper, non-provisioned way to test grounded
retrieval against real object context.
