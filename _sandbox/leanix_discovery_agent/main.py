"""Minimal Strands agent on AgentCore Runtime, deployed so SAP LeanIX's AgentCore discovery
integration has a real agent to find. Deploy and teardown: _sandbox/leanix_discovery_agent.py."""

from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

app = BedrockAgentCoreApp()
agent = Agent(
    model=BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", region_name="us-east-1"),
    system_prompt="You are a test agent used to check AI agent discovery. Answer in one short sentence.",
    callback_handler=None,
)


@app.entrypoint
def invoke(payload):
    return {"result": str(agent(payload.get("prompt", "Say hello.")))}


if __name__ == "__main__":
    app.run()
