"""
Level 10: Amazon Bedrock AgentCore Deployment
=============================================
Deploy Strands agents to production with AgentCore.

Key Concepts:
- AgentCore: Serverless runtime for AI agents
- Session isolation: Each user gets dedicated microVM
- Memory management: Built-in short/long-term context
- Observability: Tracing, logging, monitoring
- Identity: AWS IAM + third-party auth integration

Two Deployment Approaches:
1. SDK Integration (simpler) - BedrockAgentCoreApp
2. Custom FastAPI (more control) - Manual endpoints

Run locally: uv run python 04_production/agentcore_deploy.py
Deploy: See deployment instructions at bottom of file

Prerequisites:
- AWS account with AgentCore access
- pip install bedrock-agentcore (for SDK approach)
- pip install fastapi uvicorn (for custom approach)
"""

# =============================================================================
# Option A: SDK Integration (Recommended for quick deployment)
# =============================================================================

def example_sdk_approach():
    """
    Simplest way to deploy to AgentCore using the SDK.

    Install: pip install bedrock-agentcore
    """
    print("SDK Approach:")
    print("-" * 40)
    print("""
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()
agent = Agent()

@app.entrypoint
def invoke(payload):
    user_message = payload.get("prompt", "Hello")
    result = agent(user_message)
    return {"result": result.message}

if __name__ == "__main__":
    app.run()  # Handles all AgentCore protocol
""")
    print("-" * 40)
    print("Deploy with: agentcore launch")
    print()


# =============================================================================
# Option B: Custom FastAPI (Full control)
# =============================================================================

def example_fastapi_approach():
    """
    Custom FastAPI server for AgentCore.

    Requirements:
    - POST /invocations - Agent invocation endpoint
    - GET /ping - Health check endpoint
    - Port 8080
    - Platform: linux/arm64
    """
    print("FastAPI Approach:")
    print("-" * 40)
    print("""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from strands import Agent
import uvicorn

app = FastAPI(title="Strands Agent Server")
agent = Agent()

class InvocationRequest(BaseModel):
    input: dict

class InvocationResponse(BaseModel):
    output: dict

@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    try:
        prompt = request.input.get("prompt", "")
        result = agent(prompt)
        return InvocationResponse(output={"message": result.message})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ping")
async def ping():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
""")
    print("-" * 40)
    print()


# =============================================================================
# Local Testing Server (works without AWS)
# =============================================================================

def create_local_test_server():
    """
    Create a local test server that mimics AgentCore endpoints.
    This can be tested locally without AWS credentials.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
        import uvicorn
    except ImportError:
        print("Install dependencies: pip install fastapi uvicorn pydantic")
        return None

    from strands import Agent
    from strands.models.openai import OpenAIModel

    # Configure model (using local LiteLLM proxy)
    model = OpenAIModel(
        model_id="claude-sonnet-4",
        client_args={
            "base_url": "http://localhost:4000",
            "api_key": "sk-local"
        }
    )

    app = FastAPI(
        title="Strands Agent Server (Local Test)",
        description="AgentCore-compatible endpoints for local testing",
        version="1.0.0"
    )

    # Create agent with callback_handler=None for clean JSON responses
    agent = Agent(model=model, callback_handler=None)

    class InvocationRequest(BaseModel):
        input: dict

    class InvocationResponse(BaseModel):
        output: dict

    @app.post("/invocations", response_model=InvocationResponse)
    async def invoke_agent(request: InvocationRequest):
        """AgentCore-compatible invocation endpoint."""
        try:
            prompt = request.input.get("prompt", "")
            if not prompt:
                raise HTTPException(status_code=400, detail="No prompt provided")

            result = agent(prompt)
            return InvocationResponse(output={
                "message": str(result),
                "status": "success"
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/ping")
    async def ping():
        """AgentCore-compatible health check endpoint."""
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        """Root endpoint with API info."""
        return {
            "name": "Strands Agent Server",
            "version": "1.0.0",
            "endpoints": {
                "POST /invocations": "Invoke the agent",
                "GET /ping": "Health check"
            }
        }

    return app


# =============================================================================
# Dockerfile Template
# =============================================================================

def print_dockerfile():
    """Print Dockerfile template for AgentCore deployment."""
    print("Dockerfile for AgentCore:")
    print("-" * 40)
    print("""
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-cache

# Copy application code
COPY agent.py ./

# AgentCore requires port 8080
EXPOSE 8080

# Run the agent server
CMD ["uv", "run", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
""")
    print("-" * 40)
    print()


# =============================================================================
# Deployment Instructions
# =============================================================================

def print_deployment_instructions():
    """Print step-by-step deployment instructions."""
    print("=" * 60)
    print("AgentCore Deployment Instructions")
    print("=" * 60)
    print("""
*** 2026 UPDATE (verified: starter-toolkit 0.3.9 banner + @aws/agentcore npm README) ***
The Python starter-toolkit CLI is DEPRECATED in favour of @aws/agentcore — a
TypeScript/npm CLI (v0.16.0, repo aws/agentcore-cli, CDK-based):
  npm install -g @aws/agentcore   # then: agentcore create / dev / deploy / invoke
Same `agentcore` command name, so uninstall the old Python CLI to avoid clashes
(pip/pipx/uv uninstall bedrock-agentcore-starter-toolkit).

WHY (verified from the README, not inferred): the new CLI is FRAMEWORK- and
LANGUAGE-AGNOSTIC — it scaffolds/deploys Strands (Python AND TypeScript),
LangChain/LangGraph, Google ADK, and OpenAI agents across Bedrock/Anthropic/
Gemini/OpenAI. A pip-distributed Python CLI can't serve that polyglot ecosystem;
an npm/CDK CLI can deploy any-language agent. It also adds a full lifecycle
(add/remove resources, logs/traces, evals, config-bundles, recommendations).

NOT deprecated: the `bedrock-agentcore` RUNTIME SDK (Python — BedrockAgentCoreApp,
payments, memory). Only the dev/deploy TOOLING moved to npm; agent code is unchanged.
This unblocks the previously-deferred "AgentCore CLI deployment" roadmap item.
Also: the Strands SDK is now a MONOREPO (Python + TypeScript + WASM; clone tag
`python/v1.42.0`) — relevant to the L39 TypeScript-SDK framing.

1. INSTALL TOOLKIT  (deprecated Python CLI; or: npm install -g @aws/agentcore)
   pip install bedrock-agentcore-starter-toolkit

2. CONFIGURE
   agentcore configure --entrypoint agent.py

3. BUILD CONTAINER (optional, toolkit can do this)
   docker build -t my-agent:latest .

4. PUSH TO ECR
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker tag my-agent:latest <account>.dkr.ecr.<region>.amazonaws.com/my-agent:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/my-agent:latest

5. DEPLOY
   agentcore launch

6. INVOKE
   aws bedrock-agentcore-runtime invoke-agent \\
     --agent-runtime-id <runtime-id> \\
     --session-id <session-id> \\
     --payload '{"prompt": "Hello!"}'

Available Regions:
- US East (N. Virginia, Ohio)
- US West (Oregon)
- Europe (Dublin, Frankfurt)
- Asia Pacific (Mumbai, Singapore, Sydney, Tokyo)
""")
    print("=" * 60)


# =============================================================================
# v1.42 Runtime SDK features (header forwarding + class-based entrypoint)
# =============================================================================
# Exercised LOCALLY — these are SDK-level behaviors, no redeploy needed.
# Validated 2026-06-02 (bedrock-agentcore 1.12):
#   * is_forwardable_header (#483): the runtime forwards an allowlisted set of
#     inbound headers (e.g. X-Api-Key) to your entrypoint via
#     context.request_headers — but NOT x-amz-*/x-amzn-* (signing) or restricted
#     headers (Host, ...).
#   * class-based @entrypoint (#474): a bound method can be the entrypoint, so a
#     stateful class instance backs the agent (not just a module-level function).

def example_v142_runtime_features():
    """Exercise the v1.42 runtime features locally and print real results."""
    import types

    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from bedrock_agentcore.runtime.context import BedrockAgentCoreContext
    from bedrock_agentcore.runtime.models import is_forwardable_header

    print("v1.42 Runtime Features (header forwarding + class-based entrypoint):")
    print("-" * 40)

    # 1. Which inbound headers the runtime forwards to agent code.
    print("\n1. is_forwardable_header (runtime allowlist):")
    for h in ["X-Api-Key", "Authorization", "Content-Type", "Host",
              "x-amz-date", "x-amzn-trace-id",
              "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Tenant"]:
        print(f"   {'FWD ' if is_forwardable_header(h) else 'drop'}  {h}")

    # 2. Class-based entrypoint: a bound method (carries instance state).
    print("\n2. Class-based @entrypoint (bound method, #474):")
    demo_app = BedrockAgentCoreApp()

    class GreetingAgent:
        def __init__(self, greeting: str):
            self.greeting = greeting  # instance state the entrypoint uses

        def invoke(self, payload, context=None):
            # #483: the runtime forwards allowlisted request headers here.
            headers = getattr(context, "request_headers", None) or {}
            return {
                "result": f"{self.greeting}, {payload.get('name', 'world')}!",
                "saw_api_key": bool(headers.get("X-Api-Key")),
            }

    greeter = GreetingAgent("Hello")
    demo_app.entrypoint(greeter.invoke)  # pre-1.42 this rejected bound methods
    print(f"   handler 'main' registered: {'main' in demo_app.handlers}")
    print(f"   handler is the bound method: {demo_app.handlers['main'].__self__ is greeter}")

    # 3. A forwarded header reaches the entrypoint (invoked locally).
    print("\n3. context.request_headers reaches the entrypoint (#483):")
    ctx = types.SimpleNamespace(request_headers={"X-Api-Key": "sk-demo-123"})
    out = demo_app.handlers["main"]({"name": "Ada"}, ctx)
    print(f"   invoke({{'name':'Ada'}}, ctx) -> {out}")
    BedrockAgentCoreContext.set_request_headers({"X-Api-Key": "sk-ctx"})
    print(f"   BedrockAgentCoreContext round-trip -> {BedrockAgentCoreContext.get_request_headers()}")
    print()


# =============================================================================
# Demo
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Level 10: Amazon Bedrock AgentCore Deployment")
    print("=" * 60)
    print()

    # Show deployment approaches
    example_sdk_approach()
    example_fastapi_approach()
    print_dockerfile()
    print_deployment_instructions()

    # v1.42 runtime SDK features (exercised live, locally)
    example_v142_runtime_features()

    # Check if user wants to run local server
    if "--serve" in sys.argv:
        print("\nStarting local test server...")
        print("Test with: curl -X POST http://localhost:8080/invocations \\")
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"input": {"prompt": "Hello!"}}\'\n')

        app = create_local_test_server()
        if app:
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=8080)
    else:
        print("\nTo run local test server:")
        print("  uv run python 04_production/agentcore_deploy.py --serve")
        print()
        print("To test the server:")
        print('  curl -X POST http://localhost:8080/invocations \\')
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"input": {"prompt": "What is 2+2?"}}\'')
