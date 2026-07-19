# L97b: The Fair Rematch — Native MemoryManager with Real (Semantic) Recall

**Code:** `06_memory/memory_rematch_semantic.py`
**Reflection:** [`level-97b-reflection.md`](../../.claude/learnings/reflections/level-97b-reflection.md)

**Status:** Done (Tier 22, 2026-07-19, gemini-2.5-flash, SDK 1.48). Closes L97's deferred parity
question with **zero AWS** — a custom local `MemoryStore`, not a provisioned Bedrock KB.

L97 showed native `MemoryManager` scored 0.00 vs the hand-built 1.00, root-caused to
`TestMemoryStore`'s lexical recall missing the turn-2 query. Rather than provision a billable Bedrock
KB (the vended `BedrockKnowledgeBaseStore` only *attaches* to a pre-existing one), this level
implements a ~35-line `SemanticMemoryStore` — the `MemoryStore` protocol is a swappable seam —
backed by local `sentence-transformers` embeddings (already a repo dep).

| Arm | Goal-success | vs |
|-----|--------------|-----|
| A memoryless | 0.00 | — |
| B hand-built (exact-key) | 1.00 | — |
| C native + semantic store | **1.00** | C vs A p=0.0003; **C vs B p=1.0 (identical)** |

**Answer to L97's question:** native `MemoryManager` reaches **full parity** with the hand-built
stack once recall works. L97's gap was the *test store's* lexical recall, not the abstraction.

**Proof of the root cause:** the stored fact vs the turn-2 query score **cosine 0.59 (hit)**
semantically but **0 (miss)** by lexical overlap — same fact, same query, opposite recall.

**L99 carried forward:** re-testing the poison under semantic recall — a WEAK policy is hijacked
3/3 (better recall delivers the poison more reliably, no longer needing term overlap), but the
EXPLICIT deny-policy still defends 0/3. Better recall ⇒ better attack delivery *and* better
legitimate recall; the L99 policy defense is orthogonal to the recall algorithm.

**Takeaways:** the `MemoryStore` protocol is a genuine extension seam (drop-in custom store, no AWS);
the recall algorithm is the load-bearing choice, the manager abstraction is neutral; and the
cheapest experiment that answers the actual question beats billable infra scoped for a different
goal. The authentic `BedrockKnowledgeBaseStore` arm remains available as a separate session if the
AWS integration itself is the objective.
