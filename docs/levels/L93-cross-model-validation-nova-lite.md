# L93: Cross-Model Validation on Bedrock Nova Lite

**Code:** `13_quality/crossmodel_validation.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md) (cross-model section)

**Status:** Done.

Every model-sensitive finding from L78–L92 re-exercised on `amazon.nova-lite-v1:0` (a deliberately
different model family from Gemini): memory tool-use (L78), trajectory tool-args (L83), multi-turn
goal-success (L84), memory-faithfulness (L88), tool-injection safety (L89), and Nova-as-judge (L91).
**All six held → labeled framework-inherent.** Memory stores (L79/L80/L81/L90) and statistics (L85)
are model-agnostic by construction and were not re-run. Caveat recorded: two models is strong
evidence, not proof for every provider; a capability-driven failure on a weaker model is distinct
from a framework finding.
