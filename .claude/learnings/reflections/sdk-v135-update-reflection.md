# SDK v1.35 Update Reflection: L6, L15, L48 Enhanced + L57-L60 New

**Date:** 2026-04-13
**SDK Delta:** v1.30.0 → v1.35.0 (5 releases, 1 month)
**Lessons:** L6 (rewrite), L15 (enhanced +3 iters), L48 (enhanced +1 tier), L57-L60 (new)

## What We Built

7 lessons covering the SDK's major new features:

| Level | Topic | Iterations | Bugs Found |
|-------|-------|------------|------------|
| L6 | AgentAsTool / auto-wrap / preserve_context | 5 | 0 |
| L57 | Session management providers + lifecycle hooks | 4 | 1 (SessionMessage schema) |
| L58 | Sliding window per_turn + token tracking | 5 | 1 (EventLoopMetrics access) |
| L59 | Bedrock service tiers + unified routing | 4 | 0 |
| L60 | MCP elicitation protocol | 4 | 0 |

## Bugs Hit During Testing

### 1. SessionMessage.role doesn't exist (L57)
- **Assumed:** `SessionMessage.role` — a flat dataclass with role field
- **Reality:** `SessionMessage.message` is the Message dict (with `role` key); `SessionMessage` wraps it with `message_id`, `redact_message`, timestamps
- **Fix:** `session_message.message.get("role")`
- **Root cause:** Didn't probe the dataclass fields before writing code

### 2. result.metrics is not a dict (L58)
- **Assumed:** `result.metrics` returns a dict-like Usage
- **Reality:** `result.metrics` is `EventLoopMetrics` (dataclass with nested `agent_invocations` → `cycles` → `usage`)
- **Fix:** `result.metrics.latest_agent_invocation.cycles[-1].usage`
- **Root cause:** Explored `Usage` TypedDict but didn't trace the access path from `AgentResult` → `EventLoopMetrics` → `AgentInvocation` → `CycleMetrics` → `Usage`

### Pattern: Both bugs = assumed data model without probing
**Prevention:** For any new SDK type, probe with `inspect.getsource(Class)` before writing code that accesses its fields. The release notes describe WHAT changed but not the exact access path.

## Key Insights

### Agent.as_tool() is instance-only
`Agent.as_tool()` is defined on the instance, not the class. You can't do `Agent.as_tool(some_agent)`. Auto-wrapping in `tools=[]` works via ToolRegistry detecting `AgentBase` instances with `hasattr(tool, "as_tool")`.

### Tool schemas dominate token cost
Same model (haiku), same conversation length:
- Without tools: ~25-114 input tokens/turn
- With 1 simple tool: ~595-851 input tokens/turn
- Tool schema is re-sent every turn — this is why `per_turn` trimming matters for conversations WITH tools

### Cache metrics are 0 through LiteLLM proxy
`cacheReadInputTokens` and `cacheWriteInputTokens` are always 0 when going through LiteLLM. The proxy doesn't forward cache metadata from the upstream provider. Direct Anthropic/Bedrock access needed for cache visibility.

### SessionManager hook sequence is deterministic
For one agent turn: `initialize → append_message(user) → sync_agent → append_message(assistant) → sync_agent → sync_agent`. The final `sync_agent` is from `AfterInvocationEvent`. This means 3 sync operations per turn — custom repositories should be efficient.

### per_turn trimming interacts with tool calls
When an agent uses tools, a single "turn" produces multiple messages (user → assistant(tool_use) → user(tool_result) → assistant). `per_turn=True` counts MODEL calls, not conversation turns. With tool use, you get more frequent trimming than expected.

## What Worked Well
- Probe-first approach for BedrockConfig, SlidingWindow params, ToolRegistry auto-wrap — confirmed API shapes before writing code
- Testing L60 and L59 first (no/minimal LLM dependency) while waiting for proxy
- The iteration-based lesson structure makes each concept independently testable

## Phase 2 Additions (L48 + L15)

| Level | Topic | Iterations Added | Bugs Found |
|-------|-------|-----------------|------------|
| L48 | Durable execution + RepositorySessionManager | +1 tier (1b) | 1 (boto3 credential guard) |
| L15 | Context mgmt + SDK-native features | +3 iterations (6-8) | 0 |

### 3. boto3 client creation does NOT validate credentials (L48)
- **Assumed:** `_sfn_clients()` would throw if credentials were invalid
- **Reality:** boto3 Session and client creation succeeds even with expired SSO tokens; the error surfaces on the first actual API call (`iam.get_role`)
- **Fix:** Added `iam.list_roles(MaxItems=1)` as a credential probe immediately after client creation
- **Root cause:** boto3 uses lazy credential resolution — clients are just wrappers until you call an API

### 4. tiktoken underestimates by 8.6x (L15)
- **Measured:** Turn 3 of a 3-turn conversation: tiktoken estimated 12 tokens, SDK reported 103
- **Why:** tiktoken only counts message text. SDK counts: system prompt + message history + role markers + formatting + accumulated history
- **Impact:** For Horthy's 40% rule, tiktoken gives a dangerously optimistic view of context utilization

## What To Do Differently
- **Always probe dataclass fields** before assuming attribute names — `inspect.getsource()` takes 5 seconds, debugging takes 5 minutes
- **Test each iteration as you write it**, not after writing all 5 — the L57 bug would have been caught in iteration 3 instead of blocking iterations 3+4
- **Check LiteLLM proxy state first** before starting LLM-dependent work
- **boto3 client ≠ validated credentials** — always call a cheap list/describe operation to verify before running a demo
