# L15: Context Management

**Code:** `06_memory/context_management.py`
**Reflection:** [`level-15-v135-reflection.md`](../../.claude/learnings/reflections/level-15-v135-reflection.md)

### Level 15: Context Management
**Goal:** Efficient context window usage applying Horthy's 40% Rule

**Key Insight (Dexter Horthy / HumanLayer):**
- Optimal: <40% context utilization
- Warning: 40-60% (quality degrading)
- Dumb Zone: >60% (hallucinations, forgotten constraints)

**5 Iterations:**
1. Token Budget Tracker (tiktoken, utilization monitoring)
2. Rolling Summarization (sliding window + summary)
3. Hierarchical Summarization (verbatim → paragraphs → facts)
4. Selective Context Retrieval (importance scoring, budget-aware)
5. Context-Aware Agent (autonomous management)

**Key Patterns:**
```python
# Token budget (40% target)
budget = TokenBudget(model_id, target_utilization=0.4)
if budget.should_compress(messages):
    compressed = rolling_summarizer.rolling_context(messages)

# Hierarchical compression
# Recent (<10 turns): verbatim
# Medium (10-30): paragraph summaries
# Old (>30): key facts only

# Selective retrieval
# importance = relevance * recency_decay
# Fill token budget with highest-scored items
```

**XML Efficiency:** More token-efficient than JSON for structured prompts

---
