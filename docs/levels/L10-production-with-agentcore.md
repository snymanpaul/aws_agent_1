# L10: Production with AgentCore

**Code:** `04_production/agentcore_deploy.py`
**Reflection:** [`level-10-reflection.md`](../../.claude/learnings/reflections/level-10-reflection.md)

### Level 10: Production with AgentCore
**Goal:** Deploy agents at scale

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp

agent = Agent(model=model, tools=[...])
app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload):
    return str(agent(payload["prompt"]))
# Deploy via the AgentCore CLI or CDK
```

**Key Concepts:**
- Serverless deployment
- Session isolation
- Observability & monitoring
- Identity & access control

---
