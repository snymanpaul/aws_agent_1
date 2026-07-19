# Level 24: Tool Synthesis - Reflection

## Summary

Level 24 implements **runtime tool synthesis** - agents that create tools on-the-fly from natural language specifications. This is the first level in Tier 5 (Cutting Edge), building on production patterns from L21-23.

**File**: `09_cutting_edge/tool_synthesis.py` (3251 lines, 12 iterations)

## Key Patterns Learned

### Code Generation
- LLM generates Python code from `ToolSpec` (name, description, parameters, examples)
- Prompt engineering critical: system prompt defines safety rules, user prompt provides spec
- Response parsing handles multiple formats (JSON, code blocks, raw text)

### Security Layers (Defense in Depth)
1. **Syntax validation**: `compile()` catches parse errors
2. **AST validation**: Check imports, dangerous function calls
3. **Regex security scan**: Pattern matching for blocked code
4. **Capability inference**: Analyze what permissions code needs
5. **Sandbox execution**: Process or container isolation

### Sandbox Selection Strategy
```
Risk Score    Sandbox Type    Rationale
< 0.3         Subprocess      Fast (50-80ms), sufficient for safe code
>= 0.3        Docker          Secure (network=none, read-only), slower (~10s first run)
```

### Synthesis Workflow
```
generate -> validate_syntax -> security_scan -> capability_check -> test_execute -> register
```

Each step has timing, success status, and data payload for observability.

### Integration Points

| Previous Level | Pattern Used | L24 Application |
|----------------|--------------|-----------------|
| L20 Meta-Agents | TOOL_REGISTRY | `SynthesizedToolRegistry` extends pattern |
| L21 Observability | SynthesisMetrics | Step timing, success rate tracking |
| L22 Safety | Capability-based security | `CapabilityEnforcer` uses similar enum |
| L23 Recovery | Failure classification | `SynthesisFailureClassifier` for retry decisions |

## What Worked Well

1. **Layered validation** catches issues early (syntax errors before security scan)
2. **Risk-based sandbox selection** balances speed vs security
3. **Test cases in synthesis** verify generated code correctness
4. **A/B testing for versions** enables safe iteration on tools
5. **Unified facade** hides complexity for simple use cases

## What Could Be Improved

1. **Docker cold start** is slow (~10s) on first run; pre-pull images
2. **LLM code quality** varies; may need prompt iteration or model upgrade
3. **Graphiti integration** is simulated; real implementation would use MCP
4. **Resource limits** in subprocess are advisory; Docker enforces them

## 12 Iterations

| # | Name | Key Classes | Demo |
|---|------|-------------|------|
| 1 | Code Generator | `CodeGenerator`, `ToolSpec`, `GeneratedTool` | Generate compound interest calculator |
| 2 | Validation | `CodeValidator`, `SecurityScanner` | Detect dangerous code patterns |
| 3 | Subprocess Sandbox | `SubprocessSandbox`, `ResourceLimits` | Execute with timeout protection |
| 4 | Docker Sandbox | `DockerSandbox`, `SandboxFactory` | Container isolation, network disabled |
| 5 | Tool Registry | `SynthesizedToolRegistry`, `ToolLifecycleManager` | Register and invoke synthesized tools |
| 6 | Capabilities | `CapabilityInferrer`, `CapabilityEnforcer` | Block forbidden capabilities |
| 7 | Workflow | `SynthesisWorkflow`, `SynthesisVerifier` | Full pipeline with test verification |
| 8 | Observability | `TracedSynthesisWorkflow`, `SynthesisMetrics` | Span attributes, metrics collection |
| 9 | Recovery | `ResilientSynthesizer`, `SynthesisFailureClassifier` | Retry + fallback chain |
| 10 | Versioning | `ToolVersionManager`, `ABTestManager` | Version control, A/B testing |
| 11 | Persistence | `ToolGraphStore`, `ToolRecommender` | Graphiti for cross-session reuse |
| 12 | Facade | `ToolSynthesizer`, `synthesize_new_tool` | Unified entry point, self-synthesis |

## Key Code Patterns

### Security Pattern Matching
```python
BLOCKED_PATTERNS = [
    (r"\beval\s*\(", CRITICAL),      # Dynamic execution
    (r"\bos\.system\s*\(", HIGH),    # Shell commands
    (r"\bopen\s*\(", MEDIUM),        # File access
]
```

### Capability Inference
```python
# Analyze AST to determine required capabilities
if re.search(r"\bmath\.", code):
    capabilities.add(CALCULATOR)
if re.search(r"\bopen\([^)]*['\"]r", code):
    capabilities.add(FILE_READ)  # Forbidden
```

### Tool Registration
```python
# Convert synthesized code to Strands @tool
def get_strands_tool(tool_id):
    def wrapper(**kwargs):
        result = sandbox.execute(tool.source_code, tool.name, **kwargs)
        tool.metrics.invocation_count += 1
        return json.dumps(result.result)
    return tool(wrapper)
```

## Future Work (L27: AWS Tool Runtime)

Planned for a separate level:
- Lambda sandbox for tool execution
- AgentCore deployment pattern
- ECR-based tool image registry
- IAM permissions for synthesized tools
- Multi-region tool distribution

## Conclusion

Tool Synthesis enables agents to extend their capabilities at runtime, with security guaranteed through multi-layer validation and sandboxed execution. The pattern of "generate -> validate -> execute" applies broadly to any LLM code generation use case.
