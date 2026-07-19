# Note: AWS AgentCore Agent Registry — has first-class `AGENT_SKILLS`

**Date**: 2026-05-19
**Source**: hands-on validation against live AWS account `<data-account-id>` (us-east-1), admin SSO.
**Why this note**: discovered while benchmarking agent "skills" across the industry. Relevant to this project's AgentCore line (L27 deploy, L33 Policy, L34 Evaluations) — the Agent Registry is a natural sibling capability and a strong candidate for a future level.

## The finding

AWS Bedrock **AgentCore** has an **Agent Registry** — a private, governed catalog/discovery layer for agent resources. Announced 2026-04-09, Preview, 5 regions (incl. us-east-1).

It treats **skills as a first-class resource**. Verified hands-on: the `DescriptorType` enum on the registry API is:

```
['MCP', 'A2A', 'CUSTOM', 'AGENT_SKILLS']
```

So a registry record can describe an MCP server, an A2A agent, a custom resource, or an **AGENT_SKILLS** bundle — one unified catalog.

## API surface (verified)

Control plane — `bedrock-agentcore-control`:
- `CreateRegistry` / `GetRegistry` / `ListRegistries` / `UpdateRegistry` / `DeleteRegistry`
- `CreateRegistryRecord` / `GetRegistryRecord` / `ListRegistryRecords` / `UpdateRegistryRecord` / `DeleteRegistryRecord`
- `SubmitRegistryRecordForApproval` / `UpdateRegistryRecordStatus` — **governance/approval workflow**: admins approve records before they become discoverable.

Data plane — `bedrock-agentcore`:
- `SearchRegistryRecords` — semantic + keyword discovery.

`CreateRegistryRecord` fields: `registryId`, `name`, `description`, `descriptorType`, `descriptors`, `recordVersion`, `synchronizationType`, `synchronizationConfiguration`, `clientToken`.

Auth: `RegistryAuthorizerType` ∈ `{CUSTOM_JWT, AWS_IAM}`.

## How to reach it (IMPORTANT — stale-tooling trap)

The Agent Registry API was **invisible** on first probe because the local `botocore` was stale (1.42.70 — newest models ~Sept 2025; the registry shipped April 2026). `bedrock-agentcore-control` showed only 86 operations.

After `pip install -U boto3 botocore` (→ 1.43.11): **86 → 136 operations**, and the `*Registry*` ops appeared.

**Lesson**: before concluding "AWS doesn't have X", update botocore/aws-cli. A stale SDK hides recently-shipped APIs. (This happened 3× in one session — stale repo clones, stale `a2a-sdk`, stale `botocore`.)

Probe snippet:
```python
import boto3
c = boto3.client('bedrock-agentcore-control', region_name='us-east-1')
c.meta.service_model.shape_for('DescriptorType').enum
# -> ['MCP', 'A2A', 'CUSTOM', 'AGENT_SKILLS']
c.list_registries()   # [] on a fresh account — API works, nothing created yet
```

## AWS vs Google (both validated hands-on, same week)

| | Google Vertex AI Skill Registry | AWS AgentCore Agent Registry |
|---|---|---|
| Scope | Skills-only | **Unified** — MCP / A2A / CUSTOM / AGENT_SKILLS in one catalog |
| Discovery | `skills.retrieve` (semantic) | `SearchRegistryRecords` (semantic + keyword) |
| Governance | not surfaced | **built-in approval workflow** (submit → approve → discoverable) |
| Maturity | v1beta1 | Preview (Apr 2026) |
| Format | versioned zipped `SKILL.md` bundles | descriptor records (`descriptorType` + `descriptors`) |

AWS's is arguably broader: skills sit alongside MCP servers and A2A agents in one governed catalog, rather than a skills-specific registry.

## Suggested follow-up for this project

Candidate new level (Tier: AgentCore): **"AgentCore Agent Registry — publish & discover a skill"** — create a registry, add an `AGENT_SKILLS` record, submit for approval, then `SearchRegistryRecords` to discover it. Pairs naturally with the existing L30 (Strands `AgentSkills` — the *local* skills story) to contrast local-plugin skills vs cloud-registry skills.
