# Level 27: Research Agent for AWS Bedrock AgentCore
# Platform: linux/arm64 (required for AgentCore)
#
# Build:
#   docker build -t research-agent:l27 --platform linux/arm64 -f 10_production/Dockerfile .
#
# Run locally:
#   docker run -p 8080:8080 \
#     -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
#     -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
#     -e BEDROCK_REGION=us-east-1 \
#     -e PERPLEXITY_API_KEY=$PERPLEXITY_API_KEY \
#     research-agent:l27
#
# Test:
#   curl http://localhost:8080/ping
#   curl -X POST http://localhost:8080/invocations \
#     -H "Content-Type: application/json" \
#     -d '{"input": {"prompt": "What is RAG?"}}'

FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (for layer caching)
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-cache

# Copy L27 production code
COPY 10_production/bedrock_models.py ./
COPY 10_production/dynamodb_persistence.py ./
COPY 10_production/l27_agentcore_research_agent.py ./

# Copy tools directory for model utilities
COPY tools/ ./tools/

# AgentCore requires port 8080
EXPOSE 8080

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default environment (can be overridden)
ENV BEDROCK_REGION=us-east-1
ENV DYNAMODB_SESSIONS_TABLE=research_agent_sessions
ENV DYNAMODB_CHECKPOINTS_TABLE=research_agent_checkpoints
ENV ENABLE_GRAPHITI=true
ENV ENABLE_PERPLEXITY=true

# Run the research agent server
CMD ["uv", "run", "python", "l27_agentcore_research_agent.py"]
