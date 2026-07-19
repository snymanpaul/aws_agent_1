"""
Level 3: Custom Tools with @tool Decorator
==========================================
Create your own tools using the @tool decorator.

Key Concepts:
- @tool decorator converts any function to an agent tool
- Docstrings become tool descriptions (LLM uses these to decide when to call)
- Type hints enable parameter validation
- Return values feed back into agent reasoning

Run: uv run python 01_basics/custom_tools.py
"""

from strands import Agent, tool
from strands.models.openai import OpenAIModel

# Configure model
model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={
        "base_url": "http://localhost:4000",
        "api_key": "sk-local"
    }
)


# Custom tool 1: Simple lookup
@tool
def get_company_info(company_name: str) -> dict:
    """
    Get information about a company. Use this when asked about
    company details, employee counts, or headquarters locations.

    Args:
        company_name: The name of the company to look up

    Returns:
        Dictionary with company information
    """
    # Simulated database lookup
    companies = {
        "anthropic": {
            "name": "Anthropic",
            "founded": 2021,
            "headquarters": "San Francisco, CA",
            "employees": "~1000",
            "focus": "AI Safety Research"
        },
        "aws": {
            "name": "Amazon Web Services",
            "founded": 2006,
            "headquarters": "Seattle, WA",
            "employees": "~100,000+",
            "focus": "Cloud Computing"
        },
        "openai": {
            "name": "OpenAI",
            "founded": 2015,
            "headquarters": "San Francisco, CA",
            "employees": "~3000",
            "focus": "Artificial General Intelligence"
        }
    }

    key = company_name.lower().strip()
    if key in companies:
        return companies[key]
    return {"error": f"Company '{company_name}' not found in database"}


# Custom tool 2: Unit converter
@tool
def convert_temperature(value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert temperature between Celsius, Fahrenheit, and Kelvin.

    Args:
        value: The temperature value to convert
        from_unit: Source unit (celsius, fahrenheit, or kelvin)
        to_unit: Target unit (celsius, fahrenheit, or kelvin)

    Returns:
        String with the converted temperature
    """
    # Normalize unit names
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    # Convert to Celsius first (as intermediate)
    if from_unit in ["fahrenheit", "f"]:
        celsius = (value - 32) * 5 / 9
    elif from_unit in ["kelvin", "k"]:
        celsius = value - 273.15
    elif from_unit in ["celsius", "c"]:
        celsius = value
    else:
        return f"Unknown source unit: {from_unit}"

    # Convert from Celsius to target
    if to_unit in ["fahrenheit", "f"]:
        result = celsius * 9 / 5 + 32
        unit_symbol = "F"
    elif to_unit in ["kelvin", "k"]:
        result = celsius + 273.15
        unit_symbol = "K"
    elif to_unit in ["celsius", "c"]:
        result = celsius
        unit_symbol = "C"
    else:
        return f"Unknown target unit: {to_unit}"

    return f"{value} {from_unit} = {result:.2f} {unit_symbol}"


# Custom tool 3: Word analyzer
@tool
def analyze_text(text: str) -> dict:
    """
    Analyze text and return statistics like word count, character count,
    and most common words. Use for text analysis requests.

    Args:
        text: The text to analyze

    Returns:
        Dictionary with text statistics
    """
    words = text.lower().split()
    word_freq = {}
    for word in words:
        clean_word = ''.join(c for c in word if c.isalnum())
        if clean_word:
            word_freq[clean_word] = word_freq.get(clean_word, 0) + 1

    # Get top 5 words
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

    return {
        "character_count": len(text),
        "word_count": len(words),
        "unique_words": len(word_freq),
        "top_5_words": sorted_words[:5],
        "avg_word_length": sum(len(w) for w in words) / len(words) if words else 0
    }


# Create agent with custom tools
agent = Agent(
    model=model,
    tools=[get_company_info, convert_temperature, analyze_text]
)

print("=" * 60)
print("Level 3: Custom Tools with @tool Decorator")
print("=" * 60)
print()

# Test 1: Company lookup
# Agent streams output to stdout by default via PrintingCallbackHandler
print("Test 1: Company info lookup")
print("-" * 40)
agent("Tell me about Anthropic. When were they founded and what's their focus?")
print()

# Test 2: Temperature conversion
print("Test 2: Temperature conversion")
print("-" * 40)
agent("Convert 72 degrees Fahrenheit to Celsius")
print()

# Test 3: Text analysis
print("Test 3: Text analysis")
print("-" * 40)
sample_text = """
The quick brown fox jumps over the lazy dog.
The fox was quick and the dog was lazy.
"""
agent(f"Analyze this text: '{sample_text}'")
