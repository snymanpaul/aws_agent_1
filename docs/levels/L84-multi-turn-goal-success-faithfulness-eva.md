# L84: Multi-turn goal-success + faithfulness eval (depends on F2)

**Code:** `13_quality/goal_success_eval.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L84 — Multi-turn goal-success + faithfulness eval (depends on F2)
- **Closes:** `GoalSuccessRate`/`Faithfulness` referenced but never executed.
- **Empirical objective:** on a 5-turn agentic task with a known goal, run `GoalSuccessRate` +
  `Faithfulness` over real OTel spans (F2).
- **Verify:** evaluator **fails** a deliberately-sabotaged run (goal not met / unfaithful claim) and
  **passes** a good one. **Guardrail:** if ADOT proves too heavy, build a local trace-based goal judge on
  L83's JSONL — but it must read the **real trace**, not a summary.

## Foundation prerequisite

### F2 — Stand up ADOT/OTel → Application Signals (or a local OTel span store)
- **Closes:** the wall blocking `GoalSuccessRate`/`Faithfulness`/tool-accuracy (L34/L35 never executed).
- **Builds on:** `08_production/observability.py` (L21 OTel), `artifacts/adk_patterns/_trace.py`.
- **Empirical objective:** an instrumented agent emits OTel spans a trace-level evaluator can read.
- **Verify:** assert a Session/trace exists with ≥1 tool span; a TRACE_LEVEL evaluator instantiates
  without the "requires OTel Session" error. **Guardrail:** real spans, not a hand-built fixture.
