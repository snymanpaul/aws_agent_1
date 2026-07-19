# Level 25: Self-Improving Agents - Reflection

**Date**: 2025-12-14
**File**: `09_cutting_edge/self_improving.py`
**Lines**: ~3700
**Iterations**: 12

## What Was Built

A complete self-improving agent framework with 12 integrated components:

1. **PerformanceTracker** - Baseline measurement, comparison, trend detection
2. **FeedbackCollector** - Explicit/implicit signals, sentiment aggregation
3. **PromptEvolutionEngine** - Genetic algorithm with mutation, crossover, selection
4. **ExampleCurator** - Dynamic few-shot example bank with selection strategies
5. **ToolAffinityLearner** - Learn tool-task affinities from usage patterns
6. **QualityScorer** - Multi-dimensional quality evaluation (accuracy, completeness, relevance, format, safety, conciseness)
7. **ImprovementLoop** - Autonomous observe-analyze-improve-verify-commit cycle
8. **ABTestManager** - Safe A/B testing with statistical significance (z-test)
9. **LearningGraphStore** - Cross-session persistence via Graphiti MCP
10. **RegressionDetector** - Performance monitoring with auto-rollback
11. **EscalationHandler** - Human-in-the-loop for uncertainty/failures
12. **SelfImprovingAgent** - Unified facade combining all components

## Key Patterns Learned

### 1. Feedback-Driven vs Rule-Based
Self-improvement should be driven by measured performance, not hardcoded rules. The improvement loop analyzes actual bottlenecks (accuracy, sentiment, failure count) to select strategies.

### 2. Safe by Default
Multiple safety layers prevent degradation:
- **Checkpoints** before every improvement attempt
- **Verification** after improvement (before vs after comparison)
- **Regression detection** with severity classification
- **Auto-rollback** for critical regressions (>20% drop)
- **A/B testing** for safe experiments with statistical significance

### 3. Improvement Loop Phases
```
OBSERVE → ANALYZE → IMPROVE → VERIFY → COMMIT/ROLLBACK
```
Each phase is distinct and can be customized independently.

### 4. Genetic Algorithm for Prompts
Prompt evolution uses:
- **Mutation strategies**: instruction_add, constraint_add, tone_shift, example_inject, format_change, word_swap
- **Tournament selection** with elitism
- **Crossover** for combining successful prompts
- **Fitness threshold** for early stopping

### 5. Multi-Dimensional Quality
Quality is not a single number. Six dimensions:
- Accuracy (factual correctness)
- Completeness (fully addresses task)
- Relevance (stays on topic)
- Format (proper structure)
- Safety (no harmful content)
- Conciseness (appropriate brevity)

### 6. Escalation Triggers
Know when to ask humans:
- LOW_CONFIDENCE (below threshold)
- REPEATED_FAILURE (N consecutive failures)
- NOVEL_TASK (unfamiliar task type)
- HIGH_STAKES (impactful decisions)
- REGRESSION_DETECTED (performance drop)

### 7. Tool Affinity Learning
Affinity score = `0.6 * success_rate + 0.2 * speed_score + 0.2 * cost_score`

Track which tools work best for which task types, then suggest optimal tools.

## What Worked Well

1. **Unified facade pattern** - `SelfImprovingAgent` hides complexity behind clean API
2. **Incremental checkpointing** - Easy rollback when improvements fail
3. **Statistical significance** for A/B tests - Z-score > 1.96 for 95% confidence
4. **Fallback actions** for unresolved escalations - Graceful degradation
5. **Example curation** with multiple selection strategies (quality, recency, diversity, effectiveness)

## What Could Be Improved

1. **Graphiti integration is partially simulated** - Real MCP calls prepared but not executed in demo
2. **Fitness evaluator is simplified** - Production would need domain-specific evaluation
3. **Task classification is basic** - Could use embedding-based similarity
4. **No persistent checkpoints** - Currently in-memory only

## Integration Points with Previous Levels

| Level | Pattern Reused |
|-------|---------------|
| L11 | Reflection (quality scoring, iteration) |
| L20 | Meta-agents (prompt evolution, mutation) |
| L21 | Observability (tracking, metrics) |
| L22 | Safety (guardrails, escalation) |
| L23 | Recovery (rollback, checkpoints) |
| L24 | Tool synthesis (facade pattern, registry) |

## New Rules for CLAUDE.md

### Self-Improving Agents (L25)
- **Improvement loop phases**: OBSERVE → ANALYZE → IMPROVE → VERIFY → COMMIT; never skip verify
- **Checkpoint before improve**: Always save state before attempting improvement
- **Regression thresholds**: Critical (>20%), Major (10-20%), Minor (5-10%); auto-rollback on critical
- **A/B testing**: 95% confidence (z > 1.96) before promoting challenger
- **Escalation triggers**: Low confidence, repeated failure, novel task, high stakes; have fallback for each
- **Quality dimensions**: Score multiple dimensions; composite = weighted sum
- **Tool affinity**: Track success/latency/cost per tool-task pair; suggest based on affinity score
- **Feedback signals**: Explicit (positive/negative/correction) + Implicit (success/failure/retry/timeout)
- **Example selection strategies**: Quality-first, recency, diversity, effectiveness, balanced
- **Unified facade**: `SelfImprovingAgent.__call__()` tracks automatically; `.improve()` triggers cycle

## Usage Examples

```python
# Create self-improving agent
agent = SelfImprovingAgent(
    base_prompt="You are a helpful assistant.",
    config=SelfImproverConfig(
        evolution_generations=5,
        regression_critical_threshold=0.20,
        auto_rollback=True
    )
)

# Execute with automatic tracking
response = agent(task)

# Add explicit feedback
agent.add_feedback(task, response, is_positive=True)

# Trigger improvement cycle
result = agent.improve()  # Returns {improved, before, after, delta, strategy}

# Check status
status = agent.get_status()

# Manual rollback if needed
agent.rollback("checkpoint_name")
```

## Observations Captured

**15 observations** synced to Graphiti (`aws_agent_1-learnings`):

| Category | Count | Topics |
|----------|-------|--------|
| Pattern | 11 | improvement-loop-phases, checkpoint-before-improve, regression-thresholds, ab-testing-significance, quality-dimensions, tool-affinity-formula, feedback-signal-types, prompt-evolution-genetic, example-selection-strategies, escalation-triggers, unified-facade |
| Insight | 3 | feedback-driven-vs-rules, safe-by-default, pattern-reuse-across-levels |
| Mistake | 1 | token-limit-chunking |

## Files Created

- `09_cutting_edge/self_improving.py` (~3700 lines)
- `.claude/learnings/reflections/L25_self_improving.md` (this file)

## Next Steps (L26 Capstone)

Level 26 should combine all patterns into a **Research Agent**:
- Multi-agent (L18-20) for parallel research
- RAG (L13) + Graphiti (L17) for knowledge
- Planning (L19) for task decomposition
- Self-improvement (L25) for autonomous optimization
- Full observability (L21) and safety (L22)
