# Reflection: Levels 1-5 (Basics & Intermediate)

**Date:** 2025-12-10
**Scope:** Hello World → Sessions & State

---

## Key Insights

### Model Provider Abstraction
- `OpenAIModel` for OpenAI-compatible APIs (including LiteLLM proxy)
- `LiteLLMModel` for direct litellm usage (not proxies)
- Don't assume - test the actual API contract

### Default Behaviors Matter
- Strands streams to stdout via `PrintingCallbackHandler` by default
- Fighting the framework (adding `print(response)`) caused duplicate output
- **Rule:** Read framework defaults before writing code

### @tool Decorator Pattern
- Type hints + docstrings = self-documenting tools
- Docstrings are instructions to the LLM (decides when to call)
- Good docstrings → better tool selection

### System Prompts are High ROI
- Same model + different prompt = completely different behavior
- Constraints work (brevity prompts produce concise output)
- **Rule:** Try better prompt before bigger model

### Session Architecture
- Agent is stateless; session_manager holds state
- `session_id` identifies conversation, not agent instance
- Clear path: FileSessionManager → S3SessionManager → AgentCore Memory

---

## Mistakes Made

| Level | Mistake | Learning |
|-------|---------|----------|
| 1 | Used `LiteLLMModel` for proxy | Use `OpenAIModel` with custom `base_url` |
| 2 | Called `print(response)` with streaming | Choose one: streaming OR explicit print |
| 5 | Wrong `FileSessionManager` API | `session_id` goes to manager, not Agent |

---

## Patterns Established

1. **Model config helper** - `tools/models.py` centralizes proxy config
2. **Streaming by default** - Don't fight it, remove explicit prints
3. **Domain assistants** - Persona + tools = specialized helper
4. **Session isolation** - Different `session_id` = separate memory

---

## Questions for Future Levels

- How do multi-agent systems handle sessions? (orchestrator only?)
- How to handle tool errors gracefully?
- Cost/latency tracking - token accumulation in multi-turn sessions?
