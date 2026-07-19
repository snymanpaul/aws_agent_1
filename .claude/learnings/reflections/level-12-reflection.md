# Level 12: Structured Outputs - Reflection Summary

**Date**: 2025-12-11
**File**: `05_advanced/structured_outputs.py`

## What Was Built

Four demos showing type-safe agent responses with Pydantic:

1. **Basic**: PersonInfo extraction from text
2. **Nested**: JobPosting with Company → Address hierarchy
3. **Validation**: SentimentAnalysis with @field_validator auto-retry
4. **Error Handling**: StrictRating with StructuredOutputException

## Key Patterns

### Structured Output API
```python
result = agent(prompt, structured_output_model=MyModel)
data = result.structured_output  # Validated Pydantic object
```

### Nested Models
```python
class JobPosting(BaseModel):
    company: Company  # Company contains Address
    requirements: list[str]
```

### Validation with Auto-Retry
```python
@field_validator("confidence")
@classmethod
def validate_confidence(cls, v: float) -> float:
    if not 0.0 <= v <= 1.0:
        raise ValueError(...)
    return v
```

## Key Insights

### Field Descriptions as Prompts
- `Field(description='...')` guides LLM extraction
- Clear descriptions improve accuracy
- They're essentially embedded prompt engineering

### Type Safety Benefits
- IDE autocomplete on nested fields
- Compile-time error detection
- No manual JSON parsing/casting

### Clean Implementation
- No mistakes or API issues encountered
- Level 1-11 foundation knowledge enabled smooth implementation
- First-try success pattern continuing

## Observations Captured

- 5 observations added to `observations.jsonl`
- Categories: 3 patterns, 2 insights
- Topics: structured-output-api, nested-models, field-validation, field-descriptions, type-safety
