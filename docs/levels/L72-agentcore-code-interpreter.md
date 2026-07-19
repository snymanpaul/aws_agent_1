# L72: AgentCore Code Interpreter — Managed Sandbox

**Code:** `16_agentcore_tools/code_interpreter.py`
**Reflection:** [`level-72-reflection.md`](../../.claude/learnings/reflections/level-72-reflection.md)

**Status:** Done (Tier 20, live AWS; self-tearing-down).

**Empirical findings (live-validated):**
- `code_session(region)` context manager → managed isolated sandbox (kernel + filesystem).
- `execute_code` returns `stream[].result.structuredContent {stdout, stderr, exitCode}` — errors are
  data, not exceptions.
- Kernel state persists across calls (`clear_context` resets); the default sandbox had **no pip
  egress**.
- A Gemini agent computed `fib(20)=6765` via a `run_python` tool wired to the sandbox.
- **Gotcha:** `LESSON_DOTENV` injecting static `AWS_*` keys overrides SSO → `InvalidClientTokenId`;
  drop them when `AWS_PROFILE` is set.
