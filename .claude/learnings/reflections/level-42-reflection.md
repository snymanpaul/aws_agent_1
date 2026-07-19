# Level 42 Reflection: Reflexion — Iterative Self-Critique Loop
**Date:** 2026-03-18 | **File:** `12_orchestration/reflexion.py`
**Depends on:** L11 (Reflection), L12 (Structured Outputs)
**Unlocks:** L43 (Agent SOPs — formalized exit criteria in multi-agent pipelines)

---

## Part 1 — For Humans

### What We Built
A Reflexion orchestrator for code generation: Actor (sonnet) generates a Python function, Evaluator (pure Python test runner) scores it 0.0–1.0, Reflector (haiku structured output) translates failures into improvement advice, loop repeats until score ≥ threshold OR budget exhausted. Domain: `format_duration(seconds)` with zero-component suppression as the tricky edge case.

### How It Works

```
Task + accumulated critique
    │
    ▼ Actor (sonnet) — generates ```python block
extract_code() → code string
    │
    ▼ Evaluator (pure Python) — exec() in restricted namespace, runs 10 test cases
score (0.0–1.0), failures list, passes list
    │
    ├─ score >= threshold → return best, converged=True
    ├─ budget exhausted   → return best, converged=False
    │
    ▼ Reflector (haiku, structured_output_model=ReflectionOutput)
ReflectionOutput.improvement_advice
    │
    ▼ append to reflection_context → loop
```

### What Went Wrong
**Test case had a wrong expected value**: `86465 → "1d 5s"` should have been `86405 → "1d 5s"`. `86465 = 1d 1m 5s`, not `1d 5s`. The LLM generated *correct code on attempt 1*, but the test marked it wrong. The Reflector then gave advice based on wrong ground truth, which accumulated across 3 attempts and caused *regression* — attempt 4 produced `"1d 65s"` (skipped minute decomposition entirely). Fixed to `86405` and the loop converged in 1 attempt.

**Key takeaway from the failure**: Wrong Evaluator ground truth → Reflector gives wrong advice → accumulated wrong advice causes regression. The loop amplifies both correct and incorrect feedback.

### What Worked
1. **Architecture is clean**: Actor / Evaluator / Reflector separation is clear; the Evaluator being pure Python (zero LLM cost) is a genuine design win.
2. **Structured output for Reflector**: `ReflectionOutput` Pydantic model gives typed `improvement_advice` without string parsing. Required explicit "score = passed/total, range 0.0–1.0" in prompt to prevent raw counts.
3. **Accumulating context**: `reflection_context` string grows across attempts; each Actor call receives all prior critiques — straightforward to implement, correct semantics.
4. **Budget + best tracking**: Returning `ReflexionResult(best=..., converged=False)` on budget exhaustion is more useful than raising an exception — caller can inspect and decide.

### The Single Most Important Thing
The Reflexion loop cannot improve what it cannot measure correctly. The Evaluator is the load-bearing component — if it's wrong, the loop amplifies the wrongness. Before deploying Reflexion on any domain, verify the ground truth exhaustively. The LLM is often right on the first attempt; a buggy Evaluator is the most dangerous failure mode.

---

## Part 2 — For LLMs

### Architecture

```mermaid
sequenceDiagram
    participant Loop as Reflexion Loop
    participant Actor as Actor Agent<br/>(sonnet)
    participant Eval as Evaluator<br/>(pure Python)
    participant Ref as Reflector Agent<br/>(haiku, structured output)

    loop Until score >= threshold OR budget exhausted
        Loop->>Actor: task + accumulated reflection_context
        Actor-->>Loop: ```python code block
        Loop->>Eval: exec(code, restricted_ns) + run TEST_CASES
        Eval-->>Loop: score (0.0–1.0), failures[], passes[]
        alt score >= threshold
            Loop-->>Loop: return ReflexionResult(converged=True)
        else budget exhausted
            Loop-->>Loop: return ReflexionResult(converged=False, best=best_so_far)
        else continue
            Loop->>Ref: failures + passes + score
            Ref-->>Loop: ReflectionOutput(improvement_advice)
            Loop->>Loop: append critique to reflection_context
        end
    end
```

### Decision Log

| Decision | Why | Trade-off |
|----------|-----|-----------|
| Actor = sonnet, Reflector = haiku | Actor needs code quality; Reflector just translates failure text to advice | Could use same model; cost save is minor |
| Evaluator = pure Python `exec()` | 0 LLM calls for scoring; scoring is deterministic and fast | `exec()` is never fully sandboxed — acceptable for demo, not production |
| `__builtins__` whitelist | Limits blast radius of LLM-generated code | Blocks imports (no `os`, `sys`) — may cause NameError for valid functions using stdlib |
| Accumulate ALL prior critiques | Future attempts see full history, not just last | Long context → more tokens per Actor call as attempts increase |
| Return best on budget exhaustion | Caller can inspect score and decide whether to accept | Best attempt may still have score 0.0 if LLM can't extract a function |
| `ReflectionOutput` with explicit score prompt | Prevents model returning raw count (3.0 vs 0.6) | Requires careful prompt engineering |

### Pseudocode — Key Patterns

```
# Main loop
for attempt_num in 1..budget:
    prompt = task + reflection_context (if any)
    raw = actor(prompt)
    code = extract_code(raw, fn_name)  # regex: ```python block, fallback: def fn_name
    if not code: append failure to context; continue

    score, failures, passes = evaluate(code, fn_name)
    attempt = Attempt(attempt_num, code, score, failures)
    if best is None or score > best.score: best = attempt

    if score >= threshold: return ReflexionResult(best, converged=True)
    if attempt_num == budget: break  # no reflection on last attempt

    # Reflector
    ref_result = reflector(failure_summary, structured_output_model=ReflectionOutput)
    advice = ref_result.structured_output.improvement_advice
    reflection_context += f"\n--- Attempt {attempt_num} critique ---\n{failures}\nFix: {advice}"

return ReflexionResult(best, converged=False)

# Evaluator
def evaluate(code, fn_name):
    ns = {"__builtins__": {safe subset}}
    exec(code, ns)
    fn = ns.get(fn_name)
    for args, expected in TEST_CASES:
        result = fn(*args)
        failures.append(...) or passes.append(...)
    return len(passes)/len(TEST_CASES), failures, passes
```

### Observation Log

| # | Category | Topic | Observation |
|---|----------|-------|-------------|
| 1 | insight | reflexion-happy-path | When task is well-specified and tests are correct, Reflexion converges in 1 attempt — loop overhead is minimal; value is in the failure path |
| 2 | insight | reflexion-evaluator-quality | Wrong expected value in test suite caused correct LLM code to score 0.90; accumulated wrong critiques caused regression (attempt 4 was worse than attempt 1) |
| 3 | insight | reflexion-reflection-amplification | reflection_context compounds helpfully with correct advice, dangerously with wrong advice — 3 iterations of wrong critique drove the Actor to skip divmod entirely |
| 4 | pattern | reflexion-safe-exec | `exec()` with `__builtins__` whitelist is sufficient for demo code evaluation; catches NameError but not timing/resource attacks |
| 5 | pattern | reflexion-structured-output | Reflector prompt must say "score = passed/total, range 0.0–1.0" to prevent model returning raw count; access via `result.structured_output` |
| 6 | insight | reflexion-vs-l11 | L11 = one prompt exchange, stops when LLM feels done; L42 = loop with numeric threshold + retry budget — objective, measurable exit criterion |
| 7 | pattern | reflexion-budget-exhaustion | Return `ReflexionResult(best=best_so_far, converged=False)` — more useful than exception; caller inspects score and decides |

### Forward Links

- **Unlocks L43**: Agent SOPs — formalize exit criteria (pass/fail gates, retry policies) as reusable standards across multi-agent pipelines; Reflexion's numeric threshold is a primitive version of an SOP gate
- **Revisit when**: Building code generation loops, QA agents, or any pipeline where you want objective quality gates with retry; also when diagnosing why a Reflexion loop won't converge (check Evaluator ground truth first)
