# Level 26: Research Agent Capstone - Reflection

**Date**: 2025-12-15
**File**: `09_cutting_edge/research_agent.py`
**Lines**: ~2900
**Iterations**: 12

## What Was Built

An autonomous research assistant combining ALL patterns from L1-25:

1. **Data Models** - ResearchQuery, ResearchSource, ResearchFinding, ResearchReport
2. **ResearchPlanner** - DAG decomposition (L19)
3. **SourceAcquisition** - Multi-agent web search + fact-checking (L6, L18)
4. **KnowledgeSynthesizer** - REAL Graphiti MCP integration (L17)
5. **ResearchRAG** - ChromaDB document knowledge base (L13)
6. **ResearchCritic** - 6-dimension quality scoring (L11)
7. **ResearchToolSynthesizer** - Custom analysis tools (L24)
8. **ResearchImprovementLoop** - Self-improvement (L25)
9. **ResearchMemory** - Unified multi-layer memory (L16)
10. **ResearchGuardrails** - Safety validation (L22)
11. **ResearchRecovery** - Retry, circuit breaker, checkpoints (L21, L23)
12. **ResearchAgent** - Unified facade combining all components

## Key Patterns Learned

### 1. Research Quality Dimensions (6)
- Accuracy (25%): Are claims factually correct?
- Completeness (20%): Does it fully answer the question?
- Source Quality (15%): Are sources credible?
- Citation Coverage (15%): Are claims properly cited?
- Objectivity (10%): Is it balanced?
- Depth (15%): Is analysis sufficiently deep?

### 2. Citation Requirement
- Every finding MUST have `supporting_sources`
- Uncited claims marked as "opinion" with 50% confidence reduction
- CitationManager tracks and formats bibliography

### 3. Research DAG Flow
```
search → retrieve → analyze → synthesize → validate
```
Each step has `depends_on` for execution ordering.

### 4. Fact-Checking Pattern (L18 Debate)
- Advocate: Argues FOR the claim
- Skeptic: Argues AGAINST the claim
- Judge: Synthesizes verdict (supported/refuted/inconclusive)

### 5. Source Credibility Scoring
- .edu, .gov, arxiv.org: 0.9
- wikipedia.org, medium.com: 0.7
- Default: 0.6
- Blocked domains (misinformation): 0.0

### 6. Memory Layers for Research
- Working: Current session context
- Episodic: Past research events
- Semantic: Extracted facts and knowledge
- Graph: Relationships via Graphiti

### 7. Safety Guardrails
- Query validation: Blocked patterns for harmful queries
- Source validation: Unreliable domain detection
- Output validation: PII detection and redaction

## Integration Points

| Level | Pattern | L26 Usage |
|-------|---------|-----------|
| L6 | Agents-as-Tools | Source acquisition agents |
| L11 | Reflection | Quality critic with 6 dimensions |
| L13 | RAG | Document knowledge base |
| L16 | Unified Memory | Multi-layer memory facade |
| L17 | Graphiti | Knowledge graph persistence |
| L18 | Debate | Fact-checking via advocate/skeptic |
| L19 | Planning | Research task DAG |
| L21 | Observability | Checkpointing, metrics |
| L22 | Safety | Query/source/output validation |
| L23 | Recovery | Retry, circuit breaker |
| L24 | Tool Synthesis | Custom analysis tools |
| L25 | Self-Improvement | Feedback-driven optimization |

## What Worked Well

1. **Unified facade pattern** - Clean API hiding 12 subsystems
2. **Checkpoint per phase** - Easy resume after interruption
3. **6-dimension quality scoring** - Comprehensive evaluation
4. **Citation tracking** - Research credibility
5. **Safety guardrails** - Production-ready protection

## What Could Be Improved

1. ~~**Real web search integration**~~ ✅ FIXED: Now uses Perplexity via LiteLLM
2. ~~**LLM-based extraction**~~ ✅ FIXED: Real agent calls for extraction
3. **Parallel source acquisition** - Sequential in current impl
4. **Persistent checkpoints** - In-memory only

## Rewrite Session (2025-12-15)

The initial L26 implementation had simulated components despite CLAUDE.md rule.

### Fixes Applied

| Fix | Before | After |
|-----|--------|-------|
| WebSearch | Hardcoded `SearchResult` objects | Perplexity API via LiteLLM |
| LLM Extraction | Hardcoded `demo_findings` | Real Strands Agent calls |
| Fact-Checking | Simulated verdicts | Real Advocate/Skeptic/Judge debate |
| Tool Synthesis | Pre-registered demo tool | Real `CodeGenerator.synthesize()` |
| Graphiti | Returns empty `[]` | Real MCPClient.call_tool_sync() |
| Quality Loop | Single pass | Real iteration until threshold |

### Key Learnings

1. **LiteLLM Auth Header**: Always include `Authorization: Bearer sk-local` for localhost:4000 calls
2. **Perplexity Built-in Search**: Just prompt it to search - no separate API needed
3. **Fallback Chain**: Perplexity → LLM knowledge (both REAL, different sources)
4. **MCPClient Pattern**: `call_tool_sync(tool_use_id, tool_name, params)` with unique ID per call

### Demo Results (Post-Rewrite)

~~- **Quality Score**: 86%~~ (was heuristic, not real)
- **Quality Score**: 40-55% (REAL LLM critic - honest assessment)
- **Sources**: 8-10 requested per search (improved from 5)
- **Findings**: 28+ extracted via real LLM calls
- **MCP**: Real `add_memory` call confirmed
- **Iterations**: Quality loop runs 2-3 times when below 70% threshold

## Second Debug Session (2025-12-15 continued)

Additional bugs discovered during thorough validation:

### Additional Fixes

| Bug | Symptom | Fix |
|-----|---------|-----|
| Heuristic bypass | 86% inflated score | Use `evaluate()` not `_heuristic_evaluate()` |
| Score not stored | Guardrails saw 0% | Add `test_report.quality_score = quality.composite_score` |
| Attribute error | `quality.accuracy` crash | Use `dim_scores = {d.dimension: d.score for d in quality.dimensions}` |
| Component name | `source_acquisition` missing | Use `self.sources` (actual component name) |
| Weak Perplexity prompt | Only 5 generic sources | Request 8-10 academic/authoritative sources |
| No credibility passthrough | URL-only estimation | Add `SearchResult.credibility_hint` field |

### Key Insights (Second Session)

1. **Heuristics inflate scores**: 86% heuristic vs 46% real LLM - massive gap
2. **Honest evaluation matters**: LLM correctly identifies under-citation, low credibility
3. **More sources ≠ better quality**: Loop went 46% → 55% → 45% (dropped!)
4. **Perplexity prompts need specificity**: Ask for academic sources, credibility hints
5. **Component naming consistency**: Match `__init__` names with usage

## New Rules for CLAUDE.md

- **Research quality dimensions** (6): Accuracy, Completeness, Source Quality, Citation Coverage, Objectivity, Depth
- **Citation requirement**: EVERY finding MUST have `supporting_sources`
- **Fact-checking pattern**: Advocate/Skeptic/Judge (L18 debate)
- **Research DAG steps**: search → retrieve → analyze → synthesize → validate
- **Source credibility scoring**: Domain-based heuristics
- **Checkpoint per phase**: Save state for resumability
- **Guardrails for research**: Query/Source/Output validation
- **PII redaction**: SSN, email, phone, credit card patterns
- **Self-improvement for research**: Track quality, evolve prompts
- **Graphiti group IDs**: research_agent, research_knowledge, research_learnings
- **ResearchAgent API**: .research(), .provide_feedback(), .improve(), .get_performance()

## Observations Captured

| Category | Count | Topics |
|----------|-------|--------|
| Pattern | 18 | unified-facade, quality-dimensions, citation-tracking, dag-planning, fact-checking, memory-layers, credibility-scoring, guardrails, pii-redaction, checkpoint-resume, self-improvement, graphiti-integration, perplexity-via-litellm, litellm-request-format, mcp-client-sync-call, **perplexity-prompt-engineering**, **credibility-passthrough**, **warning-message-specificity** |
| Insight | 7 | capstone-integration, pattern-reuse, unified-api, perplexity-json-output, llm-fallback-chain, **honest-quality-scores**, **iteration-loop-effectiveness** |
| Mistake | 6 | litellm-auth-header, simulated-vs-real, **heuristic-bypass**, **quality-score-not-stored**, **attribute-mismatch**, **component-name-mismatch** |

## Files Created

- `09_cutting_edge/research_agent.py` (~2900 lines)
- `.claude/learnings/reflections/L26_research_agent.md`

## Final Retest (2025-12-15 18:00)

After API credit restoration, full end-to-end retest completed:

| Check | Result |
|-------|--------|
| Exit code | 0 (success) |
| Errors/Exceptions | 0 |
| All 12 iterations | ✅ Complete |
| CAPSTONE COMPLETE marker | ✅ Present |
| Real integrations | ✅ Confirmed |

**Final Demo Metrics:**
- Quality Score: 49% (real LLM critic)
- Sources: 22 (real Perplexity web search)
- Findings: 165 (real LLM extraction)
- Iterations: 2 refinement cycles
- Self-improvement: Completed with checkpoint

## Observations Captured (Final)

| Category | Count | Topics |
|----------|-------|--------|
| Pattern | 20 | unified-facade, quality-dimensions, citation-tracking, dag-planning, fact-checking, memory-layers, credibility-scoring, guardrails, pii-redaction, checkpoint-resume, self-improvement, graphiti-integration, perplexity-via-litellm, litellm-request-format, mcp-client-sync-call, perplexity-prompt-engineering, credibility-passthrough, warning-message-specificity, **retest-validation-protocol**, **quality-score-realistic-expectations** |
| Insight | 9 | capstone-integration, pattern-reuse, unified-api, perplexity-json-output, llm-fallback-chain, honest-quality-scores, iteration-loop-effectiveness, **api-credit-exhaustion-recovery**, **capstone-pattern-integration** |
| Mistake | 6 | litellm-auth-header, simulated-vs-real, heuristic-bypass, quality-score-not-stored, attribute-mismatch, component-name-mismatch |

## Capstone Summary

Level 26 successfully combines ALL patterns from L1-25:
- **Foundation** (L1-10): Basic agents, tools, prompts
- **Enhanced** (L11-13): Reflection, structured outputs, RAG
- **Memory** (L14-17): Long-term memory, context, unified, graph
- **Multi-Agent** (L18-20): Debate, planning, meta-agents
- **Production** (L21-23): Observability, safety, recovery
- **Cutting Edge** (L24-25): Tool synthesis, self-improvement

The ResearchAgent demonstrates that complex AI systems can be built by composing well-designed patterns, each addressing a specific concern while maintaining a clean unified API.

---

## 26-Level Learning Path Complete

**Total Observations Captured**: 35 for L26 alone (20 patterns, 9 insights, 6 mistakes)

**Key Takeaways**:
1. Real integrations always trump simulations - even for demos
2. LLM critics provide honest evaluation (40-55%) vs inflated heuristics (86%)
3. Unified facades hide complexity while preserving composability
4. Checkpoint/resume is critical for long-running workflows
5. End-to-end retesting catches integration issues incremental fixes miss

**Graphiti Sync**: ✅ All observations synced to `aws_agent_1-learnings` group
