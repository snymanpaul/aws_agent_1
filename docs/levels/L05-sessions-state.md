# L05: Sessions & State

**Code:** `02_intermediate/sessions.py`
**Reflection:** [`levels-1-5-reflection.md`](../../.claude/learnings/reflections/levels-1-5-reflection.md)

### Level 5: Sessions & State
**Goal:** Maintain context across interactions

```python
from strands.session.file_session_manager import FileSessionManager

agent = Agent(
    model=model,
    session_manager=FileSessionManager(
        session_id="my-session",
        storage_dir="./sessions"
    )
)
```

**Key Concepts:**
- Agent is stateless; session_manager holds state
- Same session_id = continued conversation
- Production path: FileSessionManager -> S3SessionManager -> AgentCore Memory

---
