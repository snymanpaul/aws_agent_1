"""
Model configuration helpers for connecting to LiteLLM proxy.

Your LiteLLM proxy runs at localhost:4000 with these models available:
- claude-sonnet-4: Claude Sonnet 4 (general purpose, good tool-use)
- claude-opus-4: Claude Opus 4 (complex reasoning)
- claude-haiku-4-5: Claude Haiku 4.5 (fast, cheap iterations)
- gemini/gemini-2.0-flash: Google Gemini Flash (fast)
- perplexity/sonar-reasoning: Perplexity (research tasks)

Usage:
    from tools import get_model
    model = get_model("claude-sonnet-4")
    agent = Agent(model=model)
"""

import os
from strands.models.openai import OpenAIModel

# Load env (API keys) so direct providers like Gemini can authenticate.
# Optionally chain an extra dotenv via LESSON_DOTENV=/path/to/.env (keeps
# machine-specific secret paths out of the committed code).
try:
    from dotenv import load_dotenv

    load_dotenv()  # repo-local .env, if present
    _extra_env = os.environ.get("LESSON_DOTENV")
    if _extra_env:
        load_dotenv(os.path.expanduser(_extra_env), override=False)
except ImportError:
    pass

# Default LiteLLM proxy configuration
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "sk-local")

# Available models in your LiteLLM proxy
AVAILABLE_MODELS = {
    # Anthropic Claude models
    "claude-sonnet-4": "claude-sonnet-4",
    "claude-opus-4": "claude-opus-4",
    "claude-haiku-4-5": "claude-haiku-4-5",
    "haiku": "claude-haiku-4-5",       # Short alias (Haiku 4.5, replaces deprecated 3.5)
    "claude-3-5-haiku": "claude-haiku-4-5",  # Legacy alias

    # Google models (gemini-2.0-flash retired 2026 -> default to 2.5-flash)
    "gemini-flash": "gemini/gemini-2.5-flash",
    "gemini-2.5-flash": "gemini/gemini-2.5-flash",
    "gemini-2.5-pro": "gemini/gemini-2.5-pro",
    "gemini-3-flash": "gemini/gemini-3-flash-preview",
    "gemini-3-pro": "gemini/gemini-3.0-pro",

    # OpenAI models
    "gpt-5-nano": "gpt-5-nano",

    # Perplexity models (research)
    "perplexity-reasoning": "perplexity/sonar-reasoning",
    "perplexity-pro": "perplexity/sonar-pro",
    "perplexity": "perplexity/sonar",
}


def get_model(
    model_name: str = "claude-sonnet-4",
    base_url: str | None = None,
    api_key: str | None = None,
    context_window_limit: int | None = None,
):
    """
    Get a configured model for use with Strands Agent.

    Args:
        model_name: One of the available model names (see AVAILABLE_MODELS)
        base_url: Override LiteLLM proxy URL (default: localhost:4000)
        api_key: Override API key (default: sk-local)

    Returns:
        Configured OpenAIModel ready for use with Agent()

    Example:
        model = get_model("claude-sonnet-4")
        agent = Agent(model=model, tools=[...])

    Global override:
        If the LESSON_MODEL env var is set, it overrides model_name for every
        get_model() call. This switches the whole course onto one provider
        without editing each lesson — e.g. run with
            LESSON_MODEL=gemini-2.5-flash uv run python <lesson>.py
        while the Anthropic/Claude budget is paused. Unset it to restore each
        lesson's declared model.
    """
    # Global override (see docstring) takes precedence over the requested name.
    model_name = os.environ.get("LESSON_MODEL") or model_name

    # Resolve model alias
    model_id = AVAILABLE_MODELS.get(model_name, model_name)

    # Gemini models go DIRECT to Google AI (no LiteLLM proxy needed).
    if model_id.startswith("gemini"):
        from strands.models.gemini import GeminiModel

        gem_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        gem_id = model_id.split("/", 1)[-1]  # "gemini/gemini-2.5-flash" -> "gemini-2.5-flash"
        extra = {"context_window_limit": context_window_limit} if context_window_limit else {}
        return GeminiModel(model_id=gem_id, client_args={"api_key": gem_key}, **extra)

    # Everything else: OpenAI-compatible endpoint (LiteLLM proxy).
    extra = {"context_window_limit": context_window_limit} if context_window_limit else {}
    return OpenAIModel(
        model_id=model_id,
        client_args={
            "base_url": base_url or LITELLM_BASE_URL,
            "api_key": api_key or LITELLM_API_KEY
        },
        **extra,
    )
