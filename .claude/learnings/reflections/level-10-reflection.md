# Level 10 Reflection: Amazon Bedrock AgentCore Deployment

**Date:** 2025-12-11
**File:** `04_production/agentcore_deploy.py`

## What We Built

Production deployment example with two approaches:

```mermaid
graph TB
    subgraph "Development"
        A[Strands Agent] --> L[Local Test<br/>localhost:8080]
    end

    subgraph "Deployment Options"
        SDK[SDK Approach<br/>BedrockAgentCoreApp]
        FAST[FastAPI Approach<br/>Custom Endpoints]
    end

    subgraph "AgentCore Runtime"
        AC[AgentCore]
        AC --> SI[Session Isolation<br/>MicroVM per user]
        AC --> MM[Memory<br/>Short/long-term]
        AC --> OB[Observability<br/>OpenTelemetry]
        AC --> ID[Identity<br/>IAM + OAuth]
    end

    L --> SDK
    L --> FAST
    SDK --> AC
    FAST --> AC
```

## Patterns That Worked

### 1. SDK Approach (Simplest)
```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()
agent = Agent()

@app.entrypoint
def invoke(payload):
    result = agent(payload.get("prompt", "Hello"))
    return {"result": result.message}
```

### 2. Required Endpoints
```mermaid
graph LR
    C[Client] -->|POST| I[/invocations]
    C -->|GET| P[/ping]

    I --> A[Agent Response]
    P --> H[Health Status]

    style I fill:#c8e6c9
    style P fill:#bbdefb
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/invocations` | POST | Agent invocation |
| `/ping` | GET | Health check |

### 3. Local Testing
```bash
# Start server
uv run python 04_production/agentcore_deploy.py --serve

# Test invocation
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "What is 2+2?"}}'

# Response: {"output":{"message":"4\n","status":"success"}}
```

## Insights

### 1. AgentCore Production Features

```mermaid
graph TB
    AC[AgentCore Runtime]

    AC --> F1[Session Isolation]
    AC --> F2[Memory Management]
    AC --> F3[Observability]
    AC --> F4[Identity]

    F1 --> D1[MicroVM per user<br/>Complete isolation]
    F2 --> D2[Short-term context<br/>Long-term memory]
    F3 --> D3[OpenTelemetry<br/>Tracing & logging]
    F4 --> D4[IAM + OAuth<br/>Third-party auth]
```

### 2. Deployment Toolkit Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant CLI as agentcore CLI
    participant ECR as AWS ECR
    participant AC as AgentCore

    Dev->>CLI: configure --entrypoint agent.py
    CLI->>CLI: Build container
    CLI->>ECR: Push image
    Dev->>CLI: launch
    CLI->>AC: Deploy runtime
    AC-->>Dev: Runtime ID
```

### 3. Complete Learning Progression

```mermaid
graph LR
    subgraph "01_basics"
        L1[1: Hello Agent]
        L2[2: Built-in Tools]
        L3[3: Custom Tools]
    end

    subgraph "02_intermediate"
        L4[4: System Prompts]
        L5[5: Sessions]
    end

    subgraph "03_multi_agent"
        L6[6: Agents-as-Tools]
        L7[7: Swarm]
        L8[8: Graph]
    end

    subgraph "04_production"
        L9[9: MCP]
        L10[10: AgentCore]
    end

    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7 --> L8 --> L9 --> L10

    style L10 fill:#c8e6c9,stroke:#4caf50,stroke-width:3px
```

## Summary Statistics

**Full Learning Path:**
- 10 levels completed
- 4 folders: basics, intermediate, multi-agent, production
- 50+ observations captured
- Key patterns: tool decorator, streaming, multi-agent coordination, production deployment

**Level 10 Specific:**
- 2 deployment approaches documented
- Local test server verified working
- Dockerfile template provided
- Step-by-step deployment instructions included

## Open Questions (Future Exploration)

- How to implement canary deployments with AgentCore?
- Cost optimization strategies for production agents?
- How to integrate AgentCore with existing CI/CD pipelines?
- Multi-region deployment patterns?

## Observations Logged

6 new observations added to `observations.jsonl`:
- 3 patterns (SDK approach, endpoints, local testing)
- 3 insights (AgentCore features, deployment toolkit, learning complete)
