# L35: Strands Evals SDK

**Code:** `11_platform/evals_sdk.py`
**Reflection:** [`level-35-reflection.md`](../../.claude/learnings/reflections/level-35-reflection.md)

### Level 35: Strands Evals SDK
**Goal:** Structured local evaluation experiments with auto-generated test cases and 8 evaluator types

**Depends on:** L21 (Observability), L34 (AgentCore Evals — understand cloud vs local distinction)
**Unlocks:** Validates output quality of any other level

**Evaluator taxonomy:**

| Layer | Evaluators | Measures |
|-------|-----------|---------|
| OUTPUT | Helpfulness, Faithfulness, Output (custom rubric) | Response quality |
| TRACE | ToolSelection, ToolParameter, Trajectory | Tool usage correctness |
| SESSION | Interactions, GoalSuccessRate | Conversation flow + goal |

```
# AI-powered eval SOP (4 phases):
#   1. Plan   → TopicPlanner generates topic distribution
#   2. Generate → ExperimentGenerator creates cases (30% easy / 50% medium / 20% complex)
#   3. Execute  → run agent on each case, collect traces
#   4. Report   → evaluators score results, produce metrics

# Persistence:
#   experiment.to_file("baseline_v1.json")       → version/share/CI artifact
#   Experiment.from_file("baseline_v1.json")     → reload for comparison

# L34 vs L35:
#   L34 = cloud, continuous production sampling (no manual test sets)
#   L35 = local, structured CI experiments with explicit cases
```

**Implementation file:** `11_platform/evals_sdk.py`

**Key Concepts:**
- 8 evaluators across 3 levels: OUTPUT (quality), TRACE (tool usage), SESSION (flow + goal)
- `ExperimentGenerator` + `TopicPlanner`: LLM-driven test case gen with difficulty distribution
- Eval SOP: AI-powered 4-phase (plan → generate → execute → report) via MCP or agent
- Serialization: `to_file()`/`from_file()` for versioning, sharing, CI/CD integration
- vs L34 AgentCore Evals: local = fast iteration and CI; cloud = continuous production monitoring

**Sources:**
- [Evals SDK quickstart](https://strandsagents.com/docs/user-guide/evals-sdk/quickstart/) ✓
- [Evaluators](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/) ✓
- [ExperimentGenerator](https://strandsagents.com/docs/user-guide/evals-sdk/experiment_generator/) ✓

---
