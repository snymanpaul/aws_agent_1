"""
Level 12: Structured Outputs
=============================
Type-safe agent responses using Pydantic models.

Key Concepts:
- Schema-constrained generation via structured_output_model
- Automatic validation with Pydantic
- Custom validators with auto-retry
- Nested model structures

Run: uv run python 05_advanced/structured_outputs.py
"""

import sys
sys.path.insert(0, ".")

from pydantic import BaseModel, Field, field_validator
from strands import Agent
from strands.types.exceptions import StructuredOutputException
from tools import get_model

# Use sonnet for reliable structured output generation
model = get_model("claude-sonnet-4")


# =============================================================================
# Demo 1: Basic Structured Output
# =============================================================================
class PersonInfo(BaseModel):
    """Information about a person."""
    name: str = Field(description="Full name of the person")
    age: int = Field(description="Age in years")
    occupation: str = Field(description="Current job or profession")


def basic_structured_output_demo():
    """Extract structured data from unstructured text."""
    print("\n" + "=" * 60)
    print("Demo 1: Basic Structured Output")
    print("=" * 60)

    agent = Agent(model=model, callback_handler=None)

    text = "Meet Sarah Chen, a 28-year-old data scientist working at a tech startup in Seattle."

    print(f"\nInput text: {text}")
    print("\nExtracting structured data...")

    result = agent(
        f"Extract person information from: {text}",
        structured_output_model=PersonInfo
    )

    person = result.structured_output
    print(f"\nExtracted PersonInfo:")
    print(f"  Name: {person.name}")
    print(f"  Age: {person.age}")
    print(f"  Occupation: {person.occupation}")
    print(f"  Type: {type(person).__name__}")

    return person


# =============================================================================
# Demo 2: Nested Structured Outputs
# =============================================================================
class Address(BaseModel):
    """Physical address."""
    street: str = Field(description="Street address")
    city: str = Field(description="City name")
    country: str = Field(description="Country name")


class Company(BaseModel):
    """Company information."""
    name: str = Field(description="Company name")
    industry: str = Field(description="Industry sector")
    headquarters: Address = Field(description="Company headquarters location")


class JobPosting(BaseModel):
    """Job posting with nested company info."""
    title: str = Field(description="Job title")
    salary_min: int = Field(description="Minimum salary in USD")
    salary_max: int = Field(description="Maximum salary in USD")
    company: Company = Field(description="Hiring company details")
    requirements: list[str] = Field(description="List of job requirements")


def nested_structured_output_demo():
    """Extract complex nested structures."""
    print("\n" + "=" * 60)
    print("Demo 2: Nested Structured Outputs")
    print("=" * 60)

    agent = Agent(model=model, callback_handler=None)

    text = """
    TechCorp, a leading AI company headquartered at 123 Innovation Drive,
    San Francisco, USA, is hiring a Senior ML Engineer. The role pays
    $150,000-$200,000 and requires: 5+ years Python experience,
    deep learning expertise, and a Master's degree in CS or related field.
    """

    print(f"\nInput text: {text.strip()}")
    print("\nExtracting nested structure...")

    result = agent(
        f"Extract job posting details from: {text}",
        structured_output_model=JobPosting
    )

    job = result.structured_output
    print(f"\nExtracted JobPosting:")
    print(f"  Title: {job.title}")
    print(f"  Salary: ${job.salary_min:,} - ${job.salary_max:,}")
    print(f"  Company: {job.company.name} ({job.company.industry})")
    print(f"  Location: {job.company.headquarters.city}, {job.company.headquarters.country}")
    print(f"  Requirements:")
    for req in job.requirements:
        print(f"    - {req}")

    return job


# =============================================================================
# Demo 3: Validation with Auto-Retry
# =============================================================================
class SentimentAnalysis(BaseModel):
    """Sentiment analysis result with validation."""
    text: str = Field(description="The analyzed text")
    sentiment: str = Field(description="Sentiment: positive, negative, or neutral")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    key_phrases: list[str] = Field(description="Key phrases that indicate sentiment")

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        """Ensure sentiment is one of the allowed values."""
        allowed = {"positive", "negative", "neutral"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"Sentiment must be one of {allowed}, got '{v}'")
        return v_lower

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {v}")
        return round(v, 2)


def validation_demo():
    """Demonstrate validation with automatic retry."""
    print("\n" + "=" * 60)
    print("Demo 3: Validation with Auto-Retry")
    print("=" * 60)

    agent = Agent(model=model, callback_handler=None)

    texts = [
        "I absolutely love this product! Best purchase ever!",
        "The service was okay, nothing special but not bad either.",
        "Terrible experience. Would not recommend to anyone."
    ]

    print("\nAnalyzing sentiment with validation...")

    for text in texts:
        print(f"\nText: \"{text}\"")

        result = agent(
            f"Analyze the sentiment of this text: {text}",
            structured_output_model=SentimentAnalysis
        )

        analysis = result.structured_output
        print(f"  Sentiment: {analysis.sentiment} (confidence: {analysis.confidence})")
        print(f"  Key phrases: {', '.join(analysis.key_phrases)}")

    return analysis


# =============================================================================
# Demo 4: Error Handling
# =============================================================================
class StrictRating(BaseModel):
    """Rating with strict validation that may fail."""
    score: int = Field(description="Rating score from 1 to 5")
    reason: str = Field(description="Reason for the rating")

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        """Strict validation: only 1-5 allowed."""
        if not 1 <= v <= 5:
            raise ValueError(f"Score must be 1-5, got {v}")
        return v


def error_handling_demo():
    """Demonstrate error handling for structured outputs."""
    print("\n" + "=" * 60)
    print("Demo 4: Error Handling")
    print("=" * 60)

    agent = Agent(model=model, callback_handler=None)

    # This should work fine
    print("\n[Test 1: Valid rating request]")
    try:
        result = agent(
            "Rate this restaurant on a scale of 1-5: The food was excellent, service was great.",
            structured_output_model=StrictRating
        )
        rating = result.structured_output
        print(f"  Score: {rating.score}/5")
        print(f"  Reason: {rating.reason}")
    except StructuredOutputException as e:
        print(f"  Error: {e}")

    # This tests edge case handling
    print("\n[Test 2: Ambiguous rating request]")
    try:
        result = agent(
            "Rate on 1-5: It was mediocre at best.",
            structured_output_model=StrictRating
        )
        rating = result.structured_output
        print(f"  Score: {rating.score}/5")
        print(f"  Reason: {rating.reason}")
    except StructuredOutputException as e:
        print(f"  StructuredOutputException: {e}")

    return True


# =============================================================================
# Main Demo
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Level 12: Structured Outputs with Pydantic")
    print("=" * 60)

    # Run all demos
    print("\nRunning Demo 1: Basic Structured Output...")
    result1 = basic_structured_output_demo()

    print("\nRunning Demo 2: Nested Structured Outputs...")
    result2 = nested_structured_output_demo()

    print("\nRunning Demo 3: Validation with Auto-Retry...")
    result3 = validation_demo()

    print("\nRunning Demo 4: Error Handling...")
    result4 = error_handling_demo()

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
Key Patterns:
1. Basic: Pass Pydantic model to structured_output_model parameter
2. Access: result.structured_output returns validated Python object
3. Nested: Models can contain other models for complex structures
4. Validation: @field_validator decorators enable auto-retry on failure
5. Errors: Catch StructuredOutputException for graceful handling

Benefits:
- Type safety: IDE autocomplete, type checking
- Validation: Automatic schema enforcement
- Reliability: Retry mechanism for validation failures
- Clean code: No manual JSON parsing
""")
