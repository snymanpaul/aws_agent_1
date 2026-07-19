# L39: TypeScript SDK

**Code:** `11_platform/typescript/agent.ts`
**Reflection:** [`level-39-reflection.md`](../../.claude/learnings/reflections/level-39-reflection.md)

> **Correction 2026-07-18:** the "A2A not supported in TypeScript" claim below was wrong even when
> written — the a2a module predates ts v1.4 (`strands-ts/src/a2a/`, added in upstream PR #601,
> exports A2AServer/A2AAgent/A2AExecutor). See the
> [v1.42→v1.48 delta report](../work/research/reports/2026-07-18_strands-ecosystem-delta-v142-to-v148.md)
> §5. The TS SDK has also moved well past "experimental" feature parity (memory manager,
> middleware, Cedar interventions, durable checkpoints by ts v1.10).

### Level 39: TypeScript SDK
**Goal:** Build Strands agents in TypeScript for Lambda and serverless deployments

**Depends on:** L1-3 (understand Python SDK patterns to transfer knowledge)
**Unlocks:** Node.js/Lambda deployment track (parallel to Python)

⚠️ **Status: Experimental** — "does not yet support all features available in the Python SDK." A2A not supported.

```
# Key structural differences from Python SDK:
#   Tool input schema:  Zod schema objects  (vs Python type hints + docstring)
#   Tool handler:       async function       (vs sync function with @tool decorator)
#   Agent invocation:   agent.invoke(prompt) (vs agent(prompt))
#   Lambda deployment:  native handler export pattern built-in

# Patterns available (same as Python):
#   Single agent, Agents-as-Tools, Swarm, Graph, MCP, Streaming, Hooks

# Feature gaps vs Python (experimental status):
#   A2A Protocol       → not yet supported
#   Some advanced features pending parity
```

**When to choose TypeScript over Python:**

| Criterion | TypeScript | Python |
|-----------|-----------|--------|
| Existing infra | Node.js / Lambda-first | General purpose |
| API contracts | Typed (Zod) preferred | Flexible |
| A2A support | No | Yes |
| Maturity | Experimental | Stable |

**Repo:** [strands-agents/sdk-typescript](https://github.com/strands-agents/sdk-typescript) (experimental)
**Implementation file:** `11_platform/typescript/agent.ts`

**Key Concepts:**
- Zod schemas for type-safe tool input (vs Python type hints + docstrings)
- Native Lambda handler exports for serverless deployment
- MCP, streaming, lifecycle hooks — same concepts as Python
- Feature gap vs Python: A2A unsupported; some advanced features pending
- When to choose: existing Node.js infra, Lambda-first, typed API contracts

**Sources:**
- [TypeScript SDK preview](https://aws.amazon.com/about-aws/whats-new/2025/12/typescript-strands-agents-preview/) ✓
- [strands-agents/sdk-typescript](https://github.com/strands-agents/sdk-typescript) ✓ (524★, experimental)
- [TypeScript Quickstart](https://strandsagents.com/docs/user-guide/quickstart/typescript/) ✓
- [TypeScript API Reference](https://strandsagents.com/docs/api/typescript/) ✓

---
