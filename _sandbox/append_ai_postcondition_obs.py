"""Append resolution observation for L38:ai-powered-post-conditions."""
import json
from pathlib import Path

obs = {
    "ts": "2026-03-19T00:00:00Z",
    "repo": "aws_agent_1",
    "level": 38,
    "cat": "insight",
    "topic": "ai-powered-post-conditions",
    "obs": (
        "CLOSES question at L38:ai-powered-post-conditions. "
        "PostConditionRunner treats @ai_function validators as ordinary callables — no special path. "
        "_check_condition() calls condition(result, **kwargs) via asyncio.to_thread (sync) or await (async). "
        "An @ai_function validator makes a live LLM call each time it is invoked. "
        "All validators run concurrently via asyncio.gather, so wall-clock cost per attempt is "
        "max(validator_latencies), not sum. "
        "Latency/cost concern is real: every retry re-runs ALL validators including AI-powered ones. "
        "3 validators × 3 retries = up to 9 LLM validation calls on top of the main function retries. "
        "No built-in short-circuit, cost cap, or deduplication for AI-powered validators in source. "
        "Mitigation: keep AI validators few and use cheap models (haiku); use deterministic validators "
        "for cheap checks and reserve AI validators for semantic correctness only."
    ),
    "ctx": (
        "Read ai_functions/validation/post_conditions.py — "
        "PostConditionRunner._check_condition() lines 227-268, "
        "validate() lines 185-225 (asyncio.gather), "
        "_is_async_callable() lines 42-54"
    ),
    "entities": [
        "PostConditionRunner",
        "ai_function",
        "asyncio.gather",
        "retry-loop",
        "LLM-validator-cost",
    ],
}

path = Path(".claude/learnings/observations.jsonl")
with path.open("a") as f:
    f.write(json.dumps(obs, separators=(",", ":")) + "\n")

print(f"Appended. Total lines: {sum(1 for _ in path.open())}")
print(f"Question count: {sum(1 for l in path.open() if '\"cat\":\"question\"' in l)}")
