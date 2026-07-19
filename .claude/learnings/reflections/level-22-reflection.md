# Level 22: Safety & Guardrails - Reflection

## Summary
Built production safety layer for Strands Agents with input/output validation, rate limiting, tool sandboxing, and cost controls. Implemented 12 iterations covering custom guardrails, Bedrock API integration, contextual grounding for hallucination detection, automated reasoning for policy compliance, and full ProductionSafeAgent pipeline.

## Key Discoveries

### 1. Defense in Depth (insight)
Multiple guardrail layers are essential - never trust a single check. Custom regex catches known patterns fast; Bedrock ML catches novel attacks. Hybrid approach provides both speed and coverage.

### 2. Output is Untrusted (insight)
Agent output must be filtered even when input passes all checks. Models can hallucinate harmful content or leak PII regardless of input safety. Defense in depth applies to both input AND output.

### 3. Bedrock ApplyGuardrail for Any Model (insight)
`ApplyGuardrail` API works with ANY model, not just Bedrock models. This is key for LiteLLM proxy setups - use Bedrock as external validator regardless of which LLM backend is used.

### 4. Pydantic V2 Config (mistake)
`class Config` is deprecated in Pydantic V2. Use `model_config = {"extra": "allow"}` at class level instead of inner Config class.

### 5. Contextual Grounding Qualifiers (insight)
ApplyGuardrail uses `qualifiers` array to identify content roles: `grounding_source` for reference material, `query` for user question, and no qualifier for content to validate. This enables RAG-style hallucination detection with any model.

### 6. Grounding vs Relevance Scores (insight)
Bedrock returns two scores: grounding (is response factually based on source?) and relevance (does response answer the query?). Both needed - a response can be grounded but irrelevant, or relevant but hallucinated.

### 7. Automated Reasoning Checks Satisfiability (insight)
AR uses formal logic (SAT solvers) to check LOGICAL SATISFIABILITY, not direct policy violation. A statement is "satisfiable" if there exists a valid variable assignment where it could be true - this doesn't mean the policy allows it. Think "is this logically coherent?" not "is this permitted?"

### 8. AR Cross-Region Requirement (blocker)
To attach AR to a guardrail and use via ApplyGuardrail, the guardrail must have a cross-region inference profile configured. Without this infrastructure, use the test case API directly for validation.

### 9. AR Policy Extraction from Natural Language (insight)
AR can extract formal logic rules from natural language policy documents. Our data access policy (26 lines) produced 16 rules and 31 typed variables (BOOL, INT, enums like UserRole, DataSensitivityLevel). Document structure quality affects extraction quality.

### 10. Deterministic vs Probabilistic Validation (insight)
AR is 100% deterministic - same input always produces same result. ML-based filtering (content filters, topic detection) is probabilistic. For audit/compliance requirements, AR provides explainable, repeatable proof trails.

## Patterns Established

### Prompt Injection Detection
```python
class PromptInjectionDetector:
    PATTERNS = [
        InjectionPattern(name="ignore_instructions", pattern=r"ignore\s+...", severity="CRITICAL"),
        ...
    ]
    def detect(self, text: str) -> tuple[bool, list[dict]]
    def get_severity_score(self, matches: list[dict]) -> int
```

### PII Detection & Redaction
```python
class PIIDetector:
    PII_PATTERNS = {
        PIIType.SSN: r"\b\d{3}-\d{2}-\d{4}\b",
        PIIType.EMAIL: r"\b[A-Za-z0-9._%+-]+@...",
        ...
    }
    def detect(self, text: str) -> list[PIIMatch]
    def redact(self, text: str) -> tuple[str, list[PIIMatch]]
```

### Token-Based Rate Limiting
```python
class TokenBudget:
    def __init__(self, tokens_per_minute, tokens_per_hour, tokens_per_day): ...
    def check(self, user_id: str, estimated_tokens: int) -> tuple[bool, str]
    def record(self, user_id: str, actual_tokens: int)
```

### Capability-Based Tool Sandboxing
```python
class ToolSandbox:
    def __init__(self, allowed_capabilities: set[ToolCapability]): ...
    def wrap_tool(self, tool, tool_name, required_caps) -> Callable
    # Raises CapabilityDenied if tool needs caps not in allowed set
```

### Unified Safety Stack
```python
class SafetyStack:
    def __init__(self, config: SafetyConfig): ...
    def process_input(self, user_input, user_id, session_id, model, tokens) -> SafetyResult
    def process_output(self, agent_output, session_id, model, tokens) -> SafetyResult
    def wrap_tool(self, tool, tool_name, required_caps) -> Callable
```

### Contextual Grounding Validator
```python
class ContextualGroundingValidator:
    def validate(self, source: str, query: str, response: str) -> GroundingResult:
        """Check response is grounded in source and relevant to query."""
        content = [
            {'text': {'text': source, 'qualifiers': ['grounding_source']}},
            {'text': {'text': query, 'qualifiers': ['query']}},
            {'text': {'text': response}}  # No qualifier = guard_content
        ]
        # Returns: is_grounded, is_relevant, grounding_score, relevance_score
```

### Production Safe Agent
```python
class ProductionSafeAgent:
    """9-stage safety pipeline with Strands Agent."""
    def __call__(self, prompt: str, user_id: str) -> SafeAgentResult:
        # 1. Rate limit check
        # 2. Cost budget check
        # 3-4. Input guardrail (injection + PII + Bedrock)
        # 5. Execute agent with sandboxed tools
        # 6-7. Output guardrail (content + PII + Bedrock)
        # 8. Grounding check (if RAG context provided)
        # 9. Return with full audit trail
```

### Automated Reasoning Validator
```python
class AutomatedReasoningValidator:
    """Validate statements against formal policy rules via AWS Bedrock AR."""
    def __init__(self, policy_arn: str, build_workflow_id: str): ...
    def create_test_case(self, guard_content: str, expected_result: str) -> str
    def run_test(self, test_case_id: str) -> ARTestResult
    def validate(self, statement: str) -> PolicyValidationResult
    # Returns: is_satisfiable, confidence, premises, claims, true/false scenarios
```

### Policy Compliance Agent
```python
class PolicyComplianceAgent:
    """Agent with SafetyStack + AR validation."""
    def __init__(self, model, safety_config, ar_validator): ...
    def __call__(self, prompt: str, user_id: str) -> SafeAgentResult:
        # 1-7. SafetyStack pipeline (same as ProductionSafeAgent)
        # 8. Automated Reasoning policy check
        # 9. Return with AR result in audit trail
```

## 12 Iterations Completed

1. **Prompt Injection Detection** - 12 regex patterns, severity scoring
2. **PII Detection & Redaction** - SSN, email, phone, CC, IP, DOB + Luhn validation
3. **Output Content Filtering** - 6 harmful categories with configurable thresholds
4. **Token-Based Rate Limiting** - Multi-window (minute/hour/day) + fallback models
5. **Tool Capability Sandboxing** - Capability enum, wrap_tool, audit logging
6. **Cost Controls** - Pre/post tracking, auto-fallback to cheaper models
7. **Bedrock ApplyGuardrail API (Mock)** - External validator pattern
8. **Unified SafetyStack** - Single config, full audit trail
9. **Real AWS Bedrock Guardrails (ApplyGuardrail API)** - Created guardrail g0eks1n5vxb5
10. **BedrockModel Native + Denied Topics + Word Filters** - guardrail_id during inference
11. **Contextual Grounding + ProductionSafeAgent** - Hallucination detection + full pipeline
12. **Automated Reasoning for Policy Compliance** - Formal logic validation, 16 rules from natural language policy, PolicyComplianceAgent

## Security Patterns Summary

| Layer | Purpose | Implementation |
|-------|---------|----------------|
| Input Validation | Block malicious prompts | PromptInjectionDetector + PIIDetector |
| Output Validation | Filter harmful responses | ContentFilter + PII redaction |
| Rate Limiting | Prevent abuse | TokenBudget (minute/hour/day windows) |
| Cost Controls | Budget enforcement | CostGuardrail with model fallbacks |
| Tool Sandboxing | Capability constraints | ToolSandbox with audit logging |
| External Validation | ML-based filtering | Bedrock ApplyGuardrail API |
| Formal Compliance | Deterministic policy check | Automated Reasoning test case API |

## Files Created/Modified

- `08_production/safety_guardrails.py` - ~3100 lines, 12 iterations
- `08_production/data_access_policy.txt` - Natural language policy for AR extraction
- `CLAUDE.md` - Added L22 rules
- `LEARNING_PLAN.md` - Marked L22 done

## AWS Resources Created

| Resource | ID | Region |
|----------|-----|--------|
| Bedrock Guardrail | g0eks1n5vxb5 | us-east-1 |
| Guardrail Version 1 | Content + PII | - |
| Guardrail Version 2 | + Topics + Words | - |
| Guardrail Version 3 | + Contextual Grounding | - |
| AR Policy | vcak8fgu6aec | us-east-1 |
| AR Policy Version | 1 | - |
| AR Build Workflow | d9dc4cf7-d2f8-41c6-9183-e5640186c124 | - |

**Version 1 Configuration:**
- Content Filters: HATE, INSULTS, SEXUAL, VIOLENCE, MISCONDUCT, PROMPT_ATTACK (all HIGH)
- PII: US_SOCIAL_SECURITY_NUMBER (BLOCK), CREDIT_DEBIT_CARD_NUMBER (ANONYMIZE), EMAIL (ANONYMIZE), PHONE (ANONYMIZE)

**Version 2 Configuration (added):**
- Denied Topics: illegal-drug-manufacturing, weapons-creation, financial-fraud
- Word Filters: PWNED, jailbreak, DAN mode
- Managed Word List: PROFANITY

**Version 3 Configuration (added):**
- Contextual Grounding: threshold 0.7
- Relevance Check: threshold 0.7

**AR Policy Configuration:**
- Source Document: data_access_policy.txt (RBAC, PII handling, audit, retention rules)
- Extracted Rules: 16 formal logic rules
- Extracted Variables: 31 typed variables
  - Enums: UserRole (STANDARD, ANALYST, MANAGER, ADMIN), DataSensitivityLevel (NON_SENSITIVE, AGGREGATED_PII, RAW_PII), Environment (PRODUCTION, DEVELOPMENT)
  - Booleans: is_within_business_unit, pii_access_has_justification, export_is_secured, etc.
  - Integers: export_record_count, log_retention_years, etc.

## Key AWS Learnings

1. **ApplyGuardrail vs Native Integration**: ApplyGuardrail API works with ANY model as external validator. Native integration (guardrail_id on BedrockModel) applies during inference.

2. **Guardrail Versioning**: DRAFT for testing, numbered versions (1, 2...) for production. Must explicitly create version after guardrail creation.

3. **PROMPT_ATTACK Filter**: Bedrock's ML-based prompt injection detection caught "Ignore all previous instructions" - more robust than regex patterns for novel attacks.

4. **PII Actions**: BLOCK stops request entirely, ANONYMIZE replaces PII and continues. Both trigger GUARDRAIL_INTERVENED but with different outputs.

5. **Denied Topics**: Custom topic definitions with examples improve ML classification. Topic names like "illegal-drug-manufacturing" are descriptive; definition and examples train the classifier.

6. **Word Filters**: Two types - custom words (exact match: PWNED, jailbreak) and managed lists (AWS-maintained: PROFANITY). Both detected and blocked in single API call.

7. **Channel Account Limitation**: AWS partner/distributor accounts can use Bedrock APIs (create-guardrail, apply-guardrail) but may not have model invocation access for specific models like Claude. Amazon Nova models worked.

8. **BedrockModel Native Integration**: `BedrockModel(guardrail_id=..., guardrail_version=...)` applies guardrail during inference - guardrail trace shows violations in response metadata.

9. **Inference Profile IDs**: Newer Bedrock models require inference profile IDs (`us.anthropic.claude-*`) not raw model IDs. Raw IDs return "on-demand throughput isn't supported" error.

10. **Channel Account Scope**: Channel program restrictions are vendor-specific, not account-wide. Claude blocked but Amazon Nova works. Test multiple providers before concluding full restriction.

11. **Multi-Topic Detection**: ML classifier finds semantic overlap - drug query triggered BOTH drug AND weapons topics. Robust cross-category detection.

12. **Guardrail Dual Integration Pattern**: Two valid approaches - ApplyGuardrail API (any model) vs BedrockModel native (guardrail_id). Choose based on model provider.

13. **Contextual Grounding API Pattern**: Content array uses `qualifiers` to identify roles - `grounding_source` for reference material, `query` for user question, no qualifier for content to validate. Order matters.

14. **Grounding Score Thresholds**: Default 0.7 threshold catches obvious hallucinations (fabricated facts score ~0.0) while allowing paraphrased truths (score ~0.73+). Tune based on use case strictness.

15. **Grounding Works Post-Hoc**: Unlike content filters that block immediately, grounding validation happens AFTER model response. Use for RAG pipelines to detect when model ignores provided context.

16. **SafetyResult Attribute Names**: SafetyStack returns `SafetyResult` with `allowed` (bool), `input_processed`/`output_processed` (modified text), not `action` or `processed_input`.

17. **AR Policy Workflow**: Create policy → Build from document (extract rules) → Create version → Attach to guardrail. Build workflow ID needed for test case execution.

18. **AR Cross-Region Requirement**: `ValidationException: To use Automated Reasoning checks, your guardrail must have a cross-Region inference profile.` Requires guardrail infrastructure configuration.

19. **AR Test Case API**: Alternative to guardrail attachment - create test cases directly with `create_automated_reasoning_policy_test_case` and run with `start_automated_reasoning_policy_test_workflow`.

20. **AR Satisfiability vs Violation**: SATISFIABLE means "there exists a valid variable assignment where this could be true" - NOT "this is allowed by policy". For compliance, interpret results in business context.

21. **AR Rule Extraction Quality**: Well-structured policy documents (numbered sections, clear rules, consistent terminology) produce better formal logic extraction. Our 26-line policy produced 16 rules with proper typing.

## Next Level Preview

L23: Error Recovery - Retry with backoff, fallback chains, human escalation
