# Level 19 Reflection: Planning Agents

## Core Pattern
**Planner → Executor → Verifier (→ Replanner on failure)**

Planning agents decompose goals into explicit steps before execution, enabling dependency tracking, verification, and adaptive replanning.

## 9 Iterations Summary

| Iteration | Pattern | Key Tool/Concept | Status |
|-----------|---------|------------------|--------|
| 1. Basic | Plan → Execute → Verify | calculator | completed |
| 2. Dependencies | DAG plan → Ordered execution | http_request | completed |
| 3. Software | Code planning → file_write | file_write/read | completed |
| 4. Graph Memory | Plan → Persist to Graphiti | MCP tools | completed |
| 5. Replanning | Fail → Analyze → Revise → Retry | replanner agent | completed |
| 6. Parallel DAG | Wave-based parallel execution | ThreadPoolExecutor | 1.50x speedup |
| 7. Validation | Cycle/missing dep detection | Kahn's algorithm | 4/4 tests pass |
| 8. Conditional | Branch based on results | condition field | 3 exec, 1 skip |
| 9. Production | Retry + resource constraints | ProductionExecutor | 4/4, max_workers=2 |

## Key Learnings

### Plan Structure
```python
class PlanStep(BaseModel):
    id: str
    description: str
    depends_on: list[str] = []  # DAG edges
    success_criteria: str
    status: Literal["pending", "running", "completed", "failed"]
    result: Optional[str] = None
```

### Dependency Execution Pattern
```python
def get_executable_steps(plan: Plan) -> list[PlanStep]:
    """Only execute steps whose dependencies are completed."""
    completed_ids = {s.id for s in plan.steps if s.status == "completed"}
    return [
        s for s in plan.steps
        if s.status == "pending" and all(d in completed_ids for d in s.depends_on)
    ]
```

### Agent Roles
| Agent | Purpose | Model | Tools |
|-------|---------|-------|-------|
| Planner | Decompose goals into steps | Sonnet | None |
| Executor | Follow plan, use tools | Haiku | calculator, http_request, file ops |
| Verifier | Check results meet criteria | Sonnet | file_read |
| Replanner | Analyze failure, revise | Sonnet | None |

### Replanning Pattern
```
Initial plan fails → Detect failure → Replanner analyzes →
Minimal revision (not complete rewrite) → Retry with fallback
```

## Observations

1. **JSON Plan Parsing**: LLMs reliably output JSON plans when prompted with schema
2. **Dependency DAG**: Simple `depends_on` field enables complex execution ordering
3. **Real Tools vs Simulated**: Real tool use (calculator, http_request, file_write) makes patterns concrete
4. **Failure Detection**: Check for "error", "fail", or HTTP codes in executor output
5. **Replanning Principle**: Minimal revision beats complete rewrite

## Comparison to Previous Patterns

| Pattern | L18: Debate | L19: Planning |
|---------|-------------|---------------|
| Purpose | Explore opposing viewpoints | Decompose and sequence tasks |
| Flow | Adversarial dialogue | Structured execution |
| Agents | Advocate/Skeptic/Judge | Planner/Executor/Verifier/Replanner |
| Output | Decision recommendation | Completed task with artifacts |

## Questions Answered

1. **How do planning agents differ from reflection?**
   - Planning: Decompose BEFORE execution, structured steps
   - Reflection: Iterate AFTER execution, quality improvement

2. **When to use Replanner vs Verifier?**
   - Verifier: Checks if result meets criteria (quality gate)
   - Replanner: Analyzes WHY it failed and HOW to fix

3. **DAG vs sequential?**
   - DAG enables parallel-ready steps (future optimization)
   - Sequential is simpler but blocks on each step

## Graphiti Integration

```python
planning_record = {
    "type": "planning_outcome",
    "goal": "...",
    "plan_structure": {"steps": [...], "step_count": N},
    "execution_status": "success|failure|completed_with_retry",
    "lessons_learned": "...",
    "related_topics": ["..."],
    "pattern": "planner_executor_verifier"
}
```

## Advanced Patterns (Iterations 6-8)

### Parallel DAG Execution (Iteration 6)
```python
# Wave-based execution: independent steps run in parallel
with ThreadPoolExecutor(max_workers=len(executable)) as pool:
    futures = {pool.submit(execute_step, step, context): step for step in executable}
    for future in as_completed(futures):
        step_id, result, duration = future.result()
```
**Result**: 1.84x speedup by running 3 independent steps in Wave 1

### Plan Validation (Iteration 7)
```python
# Kahn's algorithm for cycle detection via topological sort
in_degree = {s.id: len(s.depends_on) for s in plan.steps}
queue = [s.id for s in plan.steps if in_degree[s.id] == 0]
# If sorted_order != len(steps), cycle exists
```
**Checks**: Cycles, missing dependencies, self-dependencies, unreachable steps

### Conditional Branching (Iteration 8)
```python
class ConditionalPlanStep(BaseModel):
    condition: Optional[str] = None  # e.g., "step_1.contains('30')"
    status: Literal["pending", "running", "completed", "failed", "skipped"]

# Evaluate condition before execution
if not evaluate_condition(step.condition, results):
    step.status = "skipped"
```
**Pattern**: Dynamic plan execution based on runtime results

### Production-Ready Execution (Iteration 9)
```python
class ProductionExecutor:
    def __init__(self, executor_agent, max_workers=2, max_retries=3, base_delay=0.5):
        self.max_workers = max_workers  # Resource constraint
        self.max_retries = max_retries
        self.base_delay = base_delay    # Exponential backoff base

    def execute_with_retry(self, step, context):
        for attempt in range(self.max_retries + 1):
            result = self.executor(prompt)
            if not self.is_failure(result):
                return True, result, history
            # Exponential backoff: 0.5s, 1s, 2s, ...
            delay = self.base_delay * (2 ** attempt)
            time.sleep(delay)
        return False, "Max retries exceeded", history
```
**Key insight:** Create fresh Agent per thread to avoid state corruption in parallel execution.

## Files Created
- `07_advanced_multiagent/planning_agents.py` (~1890 lines)
- `07_advanced_multiagent/_sandbox/calculator.py` (generated)
- `07_advanced_multiagent/_sandbox/test_calculator.py` (generated)
