# L12: Structured Outputs

**Code:** `05_advanced/structured_outputs.py`
**Reflection:** [`level-12-reflection.md`](../../.claude/learnings/reflections/level-12-reflection.md)

### Level 12: Structured Outputs
**Goal:** Type-safe agent responses with Pydantic

```python
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    confidence: float
    sources: list[str]
```

**Key Concepts:**
- Schema-constrained generation
- Validation with retry
- Nested structured outputs

---
