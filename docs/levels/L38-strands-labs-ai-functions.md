# L38: Strands Labs — AI Functions

**Code:** `11_platform/ai_functions.py`
**Reflection:** [`level-38-reflection.md`](../../.claude/learnings/reflections/level-38-reflection.md)

### Level 38: Strands Labs — AI Functions
**Goal:** Define tool behavior in natural language via `@ai_function`; agent loop generates + self-corrects

**Depends on:** L24 (Tool Synthesis — understand the production approach before the simplified one)
**Unlocks:** Rapid prototyping path for trusted environments

Strands Labs, launched Feb 23, 2026. Experimental — separate from core SDK.

```
# Define an AI function via docstring spec:
#   @ai_function
#   def load_invoices(file_path):
#     """
#     WHAT:       Load invoice data from file_path
#     RETURNS:    DataFrame with columns: vendor(str), amount(float), date(datetime), line_items(list)
#     VALIDATES:  amount is always positive
#     """
#     (body left empty — agent generates implementation)

# Runtime loop:
#   1. Generate  → LLM writes implementation from docstring spec
#   2. Execute   → run generated code in controlled sandbox
#   3. Validate  → check conditions from docstring
#   4. Auto-retry if validation fails (no manual iteration needed)

# L24 vs L38:
#   L24 Tool Synthesis  = Docker sandbox, explicit security controls, production-grade
#   L38 @ai_function    = simpler API, faster iteration, trusted environments only
```

**Repo:** [strands-labs/ai-functions](https://github.com/strands-labs/ai-functions) (v0.1.0, Apache 2.0)
**Implementation file:** `11_platform/ai_functions.py`

**Key Concepts:**
- Docstring = implementation spec; conditions = validation contract
- Agent loop: generate → validate → auto-retry on condition failure (no manual iteration)
- Built-in guardrails: controlled code execution, restricted imports
- vs L24: `@ai_function` for rapid prototyping; L24 for security-hardened production tools
- SDK 14M+ downloads; Labs decoupled to allow faster experimentation

**Sources:**
- [strands-labs/ai-functions](https://github.com/strands-labs/ai-functions) ✓ (228★, v0.1.0, Apache 2.0)
- [Introducing Strands Labs](https://strandsagents.com/blog/introducing-strands-labs/) ✓
- [AWS OSS Blog](https://aws.amazon.com/blogs/opensource/introducing-strands-labs-get-hands-on-today-with-state-of-the-art-experimental-approaches-to-agentic-development/) ✓

---
