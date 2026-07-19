# L04: System Prompts & Personas

**Code:** `02_intermediate/system_prompts.py`
**Reflection:** [`levels-1-5-reflection.md`](../../.claude/learnings/reflections/levels-1-5-reflection.md)

### Level 4: System Prompts & Personas
**Goal:** Shape agent behavior with prompts

```python
agent = Agent(
    model=model,
    system_prompt="""You are an AWS Solutions Architect.
    Always consider cost, security, and scalability.
    Reference AWS Well-Architected Framework when appropriate."""
)
```

**Key Concepts:**
- Same model + different prompt = different behavior
- Constraints work ("be concise" -> concise output)
- Try better prompt before bigger model (high ROI)

---
