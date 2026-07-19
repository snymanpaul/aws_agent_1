# L83: Trajectory-quality + tool-argument-correctness eval

**Code:** `13_quality/trajectory_eval.py`
**Reflection:** [`level-78-87-reflection.md`](../../.claude/learnings/reflections/level-78-87-reflection.md)

### L83 — Trajectory-quality + tool-argument-correctness eval
- **Closes:** flat-tool-name trajectory; unused `ToolSelectionAccuracy`/`ToolParameterAccuracy`.
- **Builds on:** `artifacts/adk_patterns/_trace.py` (rich JSONL: tool name+input+result+order+timing),
  `11_platform/evals_sdk.py`.
- **Empirical objective:** score tool **selection**, tool **arguments**, and decision order over the
  trajectory — not just reproducibility.
- **Verify:** build 10 golden trajectories incl. ones with **wrong tool args** and **wrong order**; the
  judge ranks good > bad (rank-corr ≥ threshold) and **flags the wrong-argument call**. **Guardrail:**
  include a trajectory that's structurally complete but semantically wrong — it must score low.
