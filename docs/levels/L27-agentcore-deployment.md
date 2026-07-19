# L27: AgentCore Deployment

**Code:** `10_production/l27agentcore/src/main.py`
**Reflection:** [`level-27-v142-reflection.md`](../../.claude/learnings/reflections/level-27-v142-reflection.md)

### Level 27: AgentCore Deployment
**Goal:** Deploy Research Agent to AWS Bedrock AgentCore

Adapts L26 capstone for production AWS deployment:

**Infrastructure:**
- DynamoDB tables for session memory and checkpoints
- Bedrock models (Claude Sonnet/Haiku) instead of LiteLLM
- FastAPI wrapper with `/invocations` and `/ping` endpoints
- Docker container for AgentCore (linux/arm64)

**Files:**
| File | Purpose |
|------|---------|
| `bedrock_models.py` | Bedrock model wrapper with auto-detection |
| `dynamodb_persistence.py` | DynamoDB session/checkpoint storage |
| `l27_agentcore_research_agent.py` | Main AgentCore wrapper |
| `Dockerfile` | Container for AgentCore deployment |
| `setup_aws.sh` | AWS CLI script for infrastructure setup |
| `teardown_aws.sh` | Cleanup script |
| `deploy_config.yaml` | Environment configuration template |

**Key Patterns:**
- Environment auto-detection (AWS vs local)
- DynamoDB persistence with TTL
- Graceful degradation for Graphiti/Perplexity
- FastAPI endpoints compatible with AgentCore

**Run locally:**
```bash
uv run python 10_production/l27_agentcore_research_agent.py --demo
```

---
