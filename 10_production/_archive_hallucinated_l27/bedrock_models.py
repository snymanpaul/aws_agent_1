"""
Level 27: Bedrock Model Configuration for AgentCore Deployment

This module provides model configuration that works both locally (via LiteLLM)
and in AWS (via Bedrock SDK). Auto-detects environment and returns appropriate model.

Usage:
    from bedrock_models import get_model_for_environment

    model = get_model_for_environment("reasoning")  # Sonnet for complex tasks
    model = get_model_for_environment("fast")       # Haiku for quick iterations
    model = get_model_for_environment("critic")     # Sonnet for evaluation
"""

import os
from typing import Literal

ModelType = Literal["fast", "reasoning", "critic"]

# Environment detection
def is_aws_environment() -> bool:
    """Detect if running in AWS (Lambda, ECS, AgentCore, etc.)."""
    return any([
        os.environ.get("AWS_EXECUTION_ENV"),      # Lambda
        os.environ.get("ECS_CONTAINER_METADATA_URI"),  # ECS
        os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"),  # ECS/Fargate
        os.environ.get("AGENTCORE_EXECUTION"),    # AgentCore (custom)
    ])


# Bedrock model IDs
BEDROCK_MODELS = {
    "fast": os.environ.get(
        "BEDROCK_FAST_MODEL",
        "anthropic.claude-3-5-haiku-20241022-v1:0"
    ),
    "reasoning": os.environ.get(
        "BEDROCK_REASONING_MODEL",
        "anthropic.claude-3-5-sonnet-20241022-v2:0"
    ),
    "critic": os.environ.get(
        "BEDROCK_CRITIC_MODEL",
        "anthropic.claude-3-5-sonnet-20241022-v2:0"
    ),
}

# LiteLLM model IDs (for local development)
LITELLM_MODELS = {
    "fast": "claude-3-5-haiku",
    "reasoning": "claude-sonnet-4",
    "critic": "claude-sonnet-4",
}


def get_bedrock_model(model_type: ModelType = "reasoning"):
    """
    Get a Bedrock model for AWS deployment.

    Args:
        model_type: "fast" (Haiku), "reasoning" (Sonnet), or "critic" (Sonnet)

    Returns:
        BedrockModel configured for the specified type
    """
    from strands.models.bedrock import BedrockModel

    region = os.environ.get("BEDROCK_REGION", "us-east-1")
    model_id = BEDROCK_MODELS.get(model_type, BEDROCK_MODELS["reasoning"])

    return BedrockModel(
        model_id=model_id,
        region_name=region
    )


def get_litellm_model(model_type: ModelType = "reasoning"):
    """
    Get a LiteLLM model for local development.

    Args:
        model_type: "fast" (Haiku), "reasoning" (Sonnet), or "critic" (Sonnet)

    Returns:
        OpenAIModel configured for LiteLLM proxy
    """
    from strands.models.openai import OpenAIModel

    base_url = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
    api_key = os.environ.get("LITELLM_API_KEY", "sk-local")
    model_id = LITELLM_MODELS.get(model_type, LITELLM_MODELS["reasoning"])

    return OpenAIModel(
        model_id=model_id,
        client_args={
            "base_url": base_url,
            "api_key": api_key
        }
    )


def get_model_for_environment(model_type: ModelType = "reasoning"):
    """
    Auto-detect environment and return appropriate model.

    In AWS: Returns BedrockModel with direct SDK calls
    Local: Returns OpenAIModel pointing to LiteLLM proxy

    Args:
        model_type: "fast" (Haiku), "reasoning" (Sonnet), or "critic" (Sonnet)

    Returns:
        Model configured for the detected environment

    Example:
        model = get_model_for_environment("reasoning")
        agent = Agent(model=model)
    """
    if is_aws_environment():
        return get_bedrock_model(model_type)
    else:
        return get_litellm_model(model_type)


def get_perplexity_config() -> dict:
    """
    Get Perplexity API configuration for web search.

    Returns dict with:
        - base_url: Perplexity API URL
        - api_key: API key (required for Perplexity)
        - model: Model ID to use
        - enabled: Whether Perplexity is configured
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")

    return {
        "base_url": os.environ.get(
            "PERPLEXITY_BASE_URL",
            "https://api.perplexity.ai/chat/completions"
        ),
        "api_key": api_key,
        "model": os.environ.get("PERPLEXITY_MODEL", "sonar"),
        "enabled": bool(api_key),
    }


def get_graphiti_config() -> dict:
    """
    Get Graphiti MCP configuration for knowledge graph.

    Returns dict with:
        - mcp_url: Graphiti MCP endpoint
        - enabled: Whether Graphiti is enabled
    """
    mcp_url = os.environ.get("GRAPHITI_MCP_URL")
    enabled = os.environ.get("ENABLE_GRAPHITI", "true").lower() == "true"

    return {
        "mcp_url": mcp_url or "http://localhost:8000/mcp",
        "enabled": enabled and bool(mcp_url),
    }


# Quick test
if __name__ == "__main__":
    print("=" * 60)
    print("L27: Bedrock Model Configuration Test")
    print("=" * 60)

    print(f"\nEnvironment: {'AWS' if is_aws_environment() else 'Local'}")
    print(f"\nBedrock Models:")
    for mt, mid in BEDROCK_MODELS.items():
        print(f"  {mt}: {mid}")

    print(f"\nLiteLLM Models:")
    for mt, mid in LITELLM_MODELS.items():
        print(f"  {mt}: {mid}")

    print(f"\nPerplexity Config: {get_perplexity_config()}")
    print(f"Graphiti Config: {get_graphiti_config()}")

    # Test model creation
    print("\nTesting model creation...")
    try:
        model = get_model_for_environment("reasoning")
        print(f"  Created model: {type(model).__name__}")
        print("  OK")
    except Exception as e:
        print(f"  Error: {e}")
