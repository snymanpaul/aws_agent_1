# Level 27: REAL AWS Bedrock AgentCore Deployment - Reflection

**Date**: 2025-12-16 (Post-Correction Reflection)
**Files**: `10_production/l27agentcore/` (CLI-generated project)
**Lines**: ~2000 total (CDK + Python + Config)
**Reflection**: Captured via /reflect command

## What Was Built (CORRECTLY)

Deployed a Strands Agent to AWS Bedrock AgentCore using the **real** AgentCore architecture:

1. **agentcore CLI** - Used `agentcore create` with production template
2. **CDK Infrastructure** - `cdk deploy` for Runtime, Memory, Gateway
3. **Container-based Runtime** - Docker image auto-built and pushed to ECR
4. **Amazon Nova Model** - Used for channel program account compatibility

## What Was Hallucinated (WRONG) - Archived

Previous attempt created fake "AgentCore" with:
- Manual FastAPI with `/invocations` endpoint
- Manual DynamoDB persistence
- Manual Docker build/push
- Manual IAM role creation

**All archived to**: `10_production/_archive_hallucinated_l27/`

## Observations Captured (9 new)

| Category | Topic | Key Learning |
|----------|-------|--------------|
| mistake | agentcore-hallucination | Entire architecture was wrong; used manual FastAPI instead of BedrockAgentCoreApp |
| pattern | agentcore-real-pattern | `@app.entrypoint` decorator with `BedrockAgentCoreApp` - no manual FastAPI |
| pattern | agentcore-cli-commands | `agentcore create/dev/deploy/invoke/status/destroy` workflow |
| insight | amazon-nova-channel-accounts | Channel program accounts can't use Claude; use Amazon Nova |
| pattern | cdk-env-setup | Must export `CDK_DEFAULT_ACCOUNT` and `CDK_DEFAULT_REGION` |
| pattern | agentcore-config-sync | Update `.bedrock_agentcore.yaml` with deployed IDs after CDK |
| insight | agentcore-is-container-based | Docker is involved but managed by CDK, not manual |
| pattern | agentcore-cdk-resources | `AWS::BedrockAgentCore::*` resources for zero-console deployment |
| mistake | research-before-implement | Should have read official docs FIRST - wasted time on hallucination |

## Key Patterns Learned

### 1. BedrockAgentCoreApp Pattern (REAL)
```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload, context):
    agent = Agent(model=load_model(), tools=[...])
    result = agent(payload.get("prompt"))
    return result

if __name__ == "__main__":
    app.run()
```

### 2. AgentCore CLI Commands
```bash
# Create project with IaC
agentcore create -p myproject -t production --agent-framework Strands

# Local development with hot reload
agentcore dev -p 8080

# Deploy to AWS (via CDK)
cd cdk && npm run cdk:deploy

# Invoke deployed agent
agentcore invoke '{"prompt": "Hello"}'

# Check status
agentcore status
```

### 3. CDK Resources (IaC)
```typescript
// AWS::BedrockAgentCore::Runtime - Container runtime
// AWS::BedrockAgentCore::Memory - Built-in memory service
// AWS::BedrockAgentCore::Gateway - MCP gateway with auth
// AWS::BedrockAgentCore::RuntimeEndpoint - PROD/DEV endpoints
// AWS::Cognito::UserPool - Authentication
```

### 4. Amazon Nova for Channel Program Accounts
```python
# Channel program accounts can't invoke Anthropic Claude directly
# Use Amazon's own models instead:
MODEL_ID = "amazon.nova-lite-v1:0"  # Fast, dev
MODEL_ID = "amazon.nova-pro-v1:0"   # Production

# Test accessibility:
aws bedrock-runtime invoke-model --model-id amazon.nova-lite-v1:0 ...
```

### 5. CDK Environment Configuration
```typescript
// Must explicitly set env for CDK deploy
const deploymentProps: BaseStackProps = {
  appName: "l27agentcore",
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION
  },
}

// Export credentials before deploy:
eval $(aws configure export-credentials --format env)
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1
```

### 6. Config Sync After CDK Deploy
```yaml
# .bedrock_agentcore.yaml must be updated with deployed IDs
bedrock_agentcore:
  agent_id: l27agentcore_Agent-8SQjr5BSN3
  agent_arn: arn:aws:bedrock-agentcore:us-east-1:<data-account-id>:runtime/l27agentcore_Agent-8SQjr5BSN3
```

## Critical Insights

### 1. AgentCore IS Container-Based
Docker is still involved - but managed by CDK/AgentCore, not manually. The difference:
- **Wrong**: Manual Dockerfile, manual ECR push, manual runtime management
- **Right**: CDK auto-builds image, auto-pushes to ECR, manages runtime lifecycle

### 2. Model Access Varies by Account Type
- Standard accounts: Full Claude access via inference profiles
- Channel program accounts: Only Amazon Nova models work
- Always test model access before deployment

### 3. IaC = CDK for AgentCore
- CDK provides L1 constructs for AgentCore (`aws-cdk-lib/aws-bedrockagentcore`)
- Production template includes full IaC (Runtime, Memory, Gateway, Cognito)
- Zero console access achieved via `cdk deploy`

### 4. Strands Integration Works Seamlessly
```python
# Same Strands patterns work in AgentCore
from strands import Agent, tool
from strands.models import BedrockModel

@tool
def my_tool(x: int) -> int:
    return x * 2

agent = Agent(model=BedrockModel(...), tools=[my_tool])
```

## Files Created

| File | Purpose |
|------|---------|
| `l27agentcore/src/main.py` | AgentCore entrypoint with BedrockAgentCoreApp |
| `l27agentcore/src/model/load.py` | Amazon Nova model loader |
| `l27agentcore/cdk/` | Full CDK IaC for Runtime/Memory/Gateway |
| `l27agentcore/Dockerfile` | Container config (auto-managed by CDK) |
| `l27agentcore/.bedrock_agentcore.yaml` | AgentCore CLI config |

## Validation Results

| Test | Status | Details |
|------|--------|---------|
| Local dev server | PASS | `agentcore dev -p 8085` |
| Amazon Nova model | PASS | `amazon.nova-lite-v1:0` works |
| Tool invocation | PASS | `add_numbers` tool executed |
| CDK deploy | PASS | DockerImageStack + AgentCoreStack |
| Remote invocation | PASS | `agentcore invoke` returns correct result |
| CloudWatch logs | PASS | Available at `/aws/bedrock-agentcore/runtimes/...` |

## Lessons Learned

### CRITICAL: Don't Hallucinate Architecture
- Read official docs FIRST
- Check official samples (github.com/awslabs/amazon-bedrock-agentcore-samples)
- If uncertain, ask or research before implementing

### Model Access Testing
- Test `aws bedrock-runtime invoke-model` BEFORE writing code
- Channel program accounts have restricted access
- Amazon Nova models are universally accessible

### CDK Environment Setup
- CDK needs explicit account/region for AgentCore
- Export credentials via `aws configure export-credentials`
- Set CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION

## Summary

Level 27 **correctly** deploys a Strands Agent to AWS Bedrock AgentCore:

1. **Real CLI**: `agentcore create/dev/deploy/invoke`
2. **Real IaC**: CDK with `AWS::BedrockAgentCore::*` resources
3. **Real Model**: Amazon Nova (compatible with all account types)
4. **Zero Console Access**: Everything via CLI and CDK

The hallucinated approach (manual FastAPI/DynamoDB) was completely wrong. AgentCore is a managed service with its own SDK, CLI, and CDK constructs.

---

**Graphiti Sync**: 9 observations synced to `aws_agent_1-learnings` group ✅
- agentcore-hallucination (mistake)
- agentcore-real-pattern (pattern)
- agentcore-cli-commands (pattern)
- amazon-nova-channel-accounts (insight)
- cdk-env-setup (pattern)
- agentcore-config-sync (pattern)
- agentcore-is-container-based (insight)
- agentcore-cdk-resources (pattern)
- research-before-implement (mistake)
