# L89: Adversarial Injection Eval

**Code:** `13_quality/adversarial_injection_eval.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md) (Extension section)

**Status:** Done (extension of the L78–L87 track).

Tool-result injection eval built the right way round: the positive control proves the detector has
teeth (it fires on a deliberately-hijacked run), there are no false positives, and the headline
result is an honest negative — **gemini-2.5-flash resisted a blatant tool-result injection, hijack
rate 0.00**. Methodology lesson: a safety eval must not require the bug to exist; prove the detector
with a positive control and report model resistance as the finding. Cross-model: same resistance on
Nova Lite (L93).
