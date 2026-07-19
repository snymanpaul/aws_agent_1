"""Shared model factory for the ADK-pattern prototypes.

Default transport = the asking team's production gate:
    OpenAIModel -> OpenAI-compat endpoint (LiteLLM proxy :4000) -> gemini-2.5-flash

Provider switch (to prove the patterns are FRAMEWORK-inherent, not Gemini-specific):
    ADK_MODEL_PROVIDER=bedrock   -> AWS Bedrock (default us.anthropic.claude-haiku-4-5 inference profile)
    ADK_BEDROCK_MODEL=<id>       -> override the Bedrock model id (e.g. amazon.nova-lite-v1:0)
    AWS_REGION / AWS_PROFILE     -> standard boto credential/region resolution
The function is still named gemini() so the 8 pattern files don't change; it returns the CONFIGURED
provider's model. Topology (Graph/Swarm/agents-as-tools/hooks) is model-agnostic.
"""

import os

# --- Gemini via OpenAI-compat proxy (default) ---
BASE_URL = "http://localhost:4000"
API_KEY = "sk-local"
GEMINI_MODEL = "gemini-2.5-flash"

# --- AWS Bedrock ---
BEDROCK_MODEL = os.environ.get("ADK_BEDROCK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def _gemini(temperature: float):
    from strands.models.openai import OpenAIModel
    return OpenAIModel(
        model_id=GEMINI_MODEL,
        client_args={"base_url": BASE_URL, "api_key": API_KEY},
        params={"temperature": temperature},
    )


def _bedrock(temperature: float):
    from strands.models import BedrockModel
    return BedrockModel(model_id=BEDROCK_MODEL, region_name=BEDROCK_REGION, temperature=temperature)


def provider() -> str:
    return os.environ.get("ADK_MODEL_PROVIDER", "gemini").lower()


def gemini(temperature: float = 0.0):
    """The configured provider's model (gemini-2.5-flash by default; Bedrock if ADK_MODEL_PROVIDER=bedrock)."""
    return _bedrock(temperature) if provider() == "bedrock" else _gemini(temperature)


if __name__ == "__main__":
    from strands import Agent
    label = "bedrock:" + BEDROCK_MODEL if provider() == "bedrock" else "gemini:" + GEMINI_MODEL
    a = Agent(model=gemini(), callback_handler=None)
    print(f"model OK [{label}] ->", str(a("Reply with exactly one word: ok")).strip()[:40])
