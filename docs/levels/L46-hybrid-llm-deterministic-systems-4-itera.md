# L46: Hybrid LLM/Deterministic Systems — 4 Iterations

**Code:** `12_orchestration/hybrid_dag_graph.py`
**Reflection:** [`level-46-reflection.md`](../../.claude/learnings/reflections/level-46-reflection.md)

### Level 46: Hybrid LLM/Deterministic Systems — 4 Iterations
**Goal:** Four angles on the same problem — how do you reliably embed LLM judgment into deterministic production code without sacrificing correctness, security, or auditability?

**Depends on:** L31 (Workflow DAG), L8 (Graph routing), L6 (Agents-as-Tools), L40 (thread safety)
**Unlocks:** L47 (Human-in-the-Loop), L49 (Evals Harness)

**Research basis:** ThoughtWorks Radar — LLM Guardrails (Languages & Frameworks, Vol.31, Oct 2024, Trial); Structured Output from LLMs (Techniques, Vol.33, Nov 2025, Trial — moved from Assess)

**Files (4 iterations):**

| Iter | File | Pattern |
|------|------|---------|
| L46a | `hybrid_dag_graph.py` | `@tool` as layer boundary — LLM routes, Workflow executes |
| L46b | `hybrid_llm_in_deterministic.py` | Typed output + confidence gate + minimize LLM surface |
| L46c | `hybrid_plan_execute.py` | Constrained op vocabulary — LLM configures, code executes |
| L46d | `hybrid_trust_boundaries.py` | Input guardrails + LLM-invisible signals + fitness functions |

```mermaid
flowchart TD
    subgraph "L46a: Routing direction"
        R[Router LLM] -->|@tool boundary| W1[Workflow DAG]
        R --> W2[Workflow DAG]
    end
    subgraph "L46b: Embedding direction"
        CODE[Deterministic code] -->|judgment slot| LLM1[classify/quality LLM]
        LLM1 -->|typed dataclass| CODE
    end
    subgraph "L46c: Planning direction"
        LLM2[LLM generates plan] -->|constrained vocab| EXEC[Deterministic executor]
    end
    subgraph "L46d: Trust boundary"
        RAW[Raw input] -->|guardrail| Z1[Zone 1 only → LLM]
        Z1 -->|hard gates + fitness fns| FINAL[Final decision]
    end
```

```
# L46a: @tool as layer boundary
@tool
def run_ingest_pipeline(source: str) -> str:
    """Docstring is all LLM sees. DAG steps are invisible."""
    return _run_workflow(ingest_tasks, new_uuid())

# L46b: LLM as typed function with confidence gate
clf = classify_document(text)     # → Classification(category, confidence, reason)
if clf.confidence < 0.60: return flagged(clf.category)
qa = assess_quality(text)         # → QualityAssessment(score, recommendation)
route(qa.recommendation)

# L46c: Constrained op vocabulary
plan = llm(f"Return ops from: {OP_REGISTRY.keys()}")
ops = parse_and_repair(plan)      # fuzzy match, enum fix, drop unknowns
validate(ops)                      # reject empty / excess / missing
for op in ops: records = execute_op(op, records)

# L46d: Trust zones
request = sanitize_zone1(raw)     # strip 8 injection patterns + PII
llm_view = filter_zone2(request)  # remove fraud_flag, compliance_hold, frozen
rec = llm(risk_prompt + llm_view)
final = apply_hard_gates(rec, request)
final = apply_fitness(final, pipeline_state)
log(delta(rec, final))            # monitor override rate
```

**Key Concepts:**
- `@tool` is an architectural boundary, not just a capability hook (L46a)
- Treat LLM calls like external API calls: retry + typed output + fallback (L46b)
- Constrained op vocabulary : LLM code gen :: parameterized SQL : string concat (L46c)
- LLM-invisible signals (structural filter) > "please ignore X in prompt" (L46d)
- Fitness functions catch system-level invariants no per-call check can see (L46d)
- Decision delta log: override rate is the primary health metric for hybrid systems (L46d)

**Sources:**
- [Understanding Multi-Agent Patterns — DEV.to](https://dev.to/aws-builders/understanding-multi-agent-patterns-in-strands-agent-graph-swarm-and-workflow-4nb8) ✓
- [ThoughtWorks Radar: LLM Guardrails](https://www.thoughtworks.com/radar/languages-and-frameworks/llm-guardrails) ✓ — Trial, Languages & Frameworks, Vol.31 (Oct 2024); external validation for L46d input guardrails pattern
- [ThoughtWorks Radar: Structured Output from LLMs](https://www.thoughtworks.com/radar/techniques/structured-output-from-llms) ✓ — Trial (moved from Assess), Techniques, Vol.33 (Nov 2025); external validation for L46b typed output contract

---
