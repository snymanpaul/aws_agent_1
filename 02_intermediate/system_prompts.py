"""
Level 4: System Prompts & Personas
==================================
Shape agent behavior using system prompts to create specialized personas.

Key Concepts:
- System prompts define agent personality and behavior
- Use them to set constraints, guidelines, and expertise areas
- Different prompts create entirely different agent behaviors
- Combine with tools for domain-specific assistants

Run: uv run python 02_intermediate/system_prompts.py
"""

from strands import Agent
from strands.models.openai import OpenAIModel
from strands_tools import calculator

# Configure model
model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={
        "base_url": "http://localhost:4000",
        "api_key": "sk-local"
    }
)

# =============================================================================
# Example 1: AWS Solutions Architect Persona
# =============================================================================

AWS_ARCHITECT_PROMPT = """You are an experienced AWS Solutions Architect with deep expertise in:
- Cloud architecture design and best practices
- AWS Well-Architected Framework (5 pillars)
- Cost optimization strategies
- Security and compliance
- High availability and disaster recovery

When answering questions:
1. Always consider the 5 pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization
2. Provide specific AWS service recommendations
3. Mention potential trade-offs and alternatives
4. Keep responses practical and actionable
5. Use bullet points for clarity

If asked about non-AWS topics, politely redirect to AWS-related solutions."""

print("=" * 70)
print("Level 4: System Prompts & Personas")
print("=" * 70)
print()

print("Example 1: AWS Solutions Architect")
print("-" * 50)
aws_architect = Agent(model=model, system_prompt=AWS_ARCHITECT_PROMPT)
aws_architect("I need to deploy a web application that handles 10,000 concurrent users. What AWS services should I use?")
print()

# =============================================================================
# Example 2: Code Reviewer Persona
# =============================================================================

CODE_REVIEWER_PROMPT = """You are a senior software engineer conducting code reviews. Your approach:

**Review Style:**
- Be constructive and educational, not critical
- Explain the "why" behind suggestions
- Prioritize: Security > Correctness > Performance > Style

**When reviewing code:**
1. First acknowledge what's done well
2. Identify potential bugs or security issues
3. Suggest improvements with examples
4. Note any missing error handling
5. Comment on readability and maintainability

**Format your review as:**
- Summary (1-2 sentences)
- What's good
- Suggestions for improvement
- Overall assessment"""

print("Example 2: Code Reviewer")
print("-" * 50)
code_reviewer = Agent(model=model, system_prompt=CODE_REVIEWER_PROMPT)

sample_code = '''
def get_user(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    result = cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return result.fetchone()
'''

code_reviewer(f"Please review this Python function:\n```python{sample_code}```")
print()

# =============================================================================
# Example 3: Financial Advisor with Calculator Tool
# =============================================================================

FINANCIAL_ADVISOR_PROMPT = """You are a certified financial advisor helping with personal finance decisions.

**Your expertise:**
- Investment strategies and portfolio allocation
- Retirement planning (401k, IRA, Roth)
- Tax optimization
- Debt management
- Budgeting and savings

**Guidelines:**
1. Always ask clarifying questions if needed
2. Use the calculator tool for precise calculations
3. Explain your reasoning and assumptions
4. Mention risks and disclaimers
5. Suggest consulting a licensed professional for major decisions

**Important:** You provide educational information, not personalized financial advice.
Always remind users to consult with a licensed financial advisor for their specific situation."""

print("Example 3: Financial Advisor (with calculator tool)")
print("-" * 50)
financial_advisor = Agent(
    model=model,
    system_prompt=FINANCIAL_ADVISOR_PROMPT,
    tools=[calculator]
)
financial_advisor(
    "If I save $500/month for 30 years at 7% annual return, "
    "how much will I have for retirement? What if I increase to $750/month?"
)
print()

# =============================================================================
# Example 4: Concise Assistant (Brevity Constraint)
# =============================================================================

CONCISE_PROMPT = """You are a concise assistant. Your responses must be:
- Maximum 2-3 sentences
- No bullet points or lists
- Direct and to the point
- No unnecessary preamble or conclusions

If a question requires a longer answer, provide the most essential information only."""

print("Example 4: Concise Assistant (brevity constraint)")
print("-" * 50)
concise_agent = Agent(model=model, system_prompt=CONCISE_PROMPT)
concise_agent("Explain what machine learning is.")
print()

print("=" * 70)
print("Key Takeaway: Same model, different system prompts = different behaviors")
print("=" * 70)
