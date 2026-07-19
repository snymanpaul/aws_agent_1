# Level 18 Reflection: Debate Pattern

**Date:** 2025-12-12
**File:** `07_advanced_multiagent/debate_pattern.py`

## Summary

Implemented the Debate Pattern for adversarial agent collaboration across **5 iterations**: basic debate, multi-round with scoring, code review application, graph memory integration, and full Graphiti round-trip.

## Key Findings

### Debate Pattern Structure
| Component | Role | System Prompt Focus |
|-----------|------|---------------------|
| **Advocate** | Argue FOR | Benefits, opportunities, evidence, success factors |
| **Skeptic** | Argue AGAINST | Risks, costs, failures, alternatives |
| **Judge** | Synthesize | Balanced analysis, strongest points, mitigations |

### Iteration Results
| # | Name | Key Learning |
|---|------|--------------|
| 1 | Basic Debate | Sequential flow works; single pass may miss nuances |
| 2 | Multi-Round | Structured turns with scoring; Skeptic often wins on thoroughness |
| 3 | Code Review | Defender/Critic/Reviewer variant; practical for dev workflows |
| 4 | Graph Memory | JSON structure for Graphiti persistence; enables cross-session learning |
| 5 | Round-Trip | Full persist → retrieve → inform workflow; Judge references past debates |

### Comparison to Other Patterns
| Pattern | Flow | Best For |
|---------|------|----------|
| Agents-as-Tools (L6) | Hierarchical | Clear delegation, specialist tasks |
| Swarm (L7) | Peer-to-peer handoffs | Complex workflows, autonomous routing |
| Reflection (L11) | Self-critique loop | Quality improvement, convergence |
| **Debate (L18)** | Adversarial dialogue | Decision analysis, risk discovery |

### Mistakes Made
1. **None significant** - Built on patterns from L6, L7, L11; familiar territory

### Patterns Discovered
1. **Adversarial prompts**: Clearly assigning FOR/AGAINST roles produces genuine opposition
2. **Judge synthesis**: Separate judge agent provides more balanced outcomes than self-synthesis
3. **Multi-round scoring**: Tracking round winners creates accountability and engagement
4. **Domain-specific variants**: Defender/Critic/Reviewer maps naturally to code review

### Surprising Insights
1. **Skeptic thoroughness**: In multi-round debates, the Skeptic often won by raising more specific concerns
2. **Code review fit**: Debate pattern naturally maps to code review (Defender = author, Critic = reviewer)
3. **Low complexity**: Pattern is simpler than Swarm or Graph; just orchestrated agent calls

## Files Modified
- `07_advanced_multiagent/__init__.py` - Created (new directory)
- `07_advanced_multiagent/debate_pattern.py` - Created (~480 lines, 5 iterations)
- `CLAUDE.md` - Updated with L17-18 learned rules

## All 5 Iterations
| # | Name | Key Takeaway |
|---|------|--------------|
| 1 | Basic Debate | Sequential Advocate → Skeptic → Judge; good for quick decisions |
| 2 | Multi-Round | Structured turns with scoring; thorough but higher cost |
| 3 | Code Review | Defender/Critic/Reviewer; practical dev workflow application |
| 4 | Graph Memory | JSON structure for Graphiti; enables cross-session pattern learning |
| 5 | Round-Trip | Retrieve past debates → inform Judge → persist new; builds org knowledge |

## Answered Questions
1. **When to use Debate vs Reflection?** Debate for exploring opposing viewpoints; Reflection for iterative quality improvement
2. **How to structure multi-round?** Each side responds to the other; Judge scores after each round
3. **Code review mapping?** Defender (author), Critic (reviewer), Judge (senior reviewer)
4. **How to build cross-session context?** Search past debates → inject into Judge system prompt → persist new debate with `related_debates` field

## Graphiti Integration Verified
- **Episodes persisted:** 3 (TypeScript, Microservices, Monorepo debates)
- **Facts extracted:** ADVOCATE_POINTS, SKEPTIC_POINTS, RECOMMENDATION with temporal metadata
- **Search works:** `search_memory_facts` retrieves relevant debate facts
- **Round-trip complete:** Judge references `RELATES_TO: PAST_DEBATE_1, PAST_DEBATE_2`

## Observations Count
- **Mistakes:** 0
- **Patterns:** 5 (+1 for round-trip pattern)
- **Insights:** 4 (+1 for Graphiti fact extraction)
- **Total:** 9 observations captured
