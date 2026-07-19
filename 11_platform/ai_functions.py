"""
Level 38: Strands Labs — AI Functions
======================================
@ai_function turns a Python function's docstring into an LLM prompt.
The agent generates output matching the return type annotation; post_conditions
validate it and trigger auto-retry on failure — all without writing agent boilerplate.

Key concepts:
  - Docstring = prompt template; {param_name} placeholders filled from args
  - Return type annotation = output schema (str, int, Pydantic model, etc.)
  - CodeExecutionMode.DISABLED → structured output from LLM (default, no code exec)
  - CodeExecutionMode.LOCAL → smolagents AST executor; agent writes+runs Python code
  - post_conditions → validation functions that return PostConditionResult;
      failure feeds the error back into the conversation and retries automatically
  - AIFunction implements ToolProvider → usable as a tool in a parent Strands Agent
  - max_attempts=10 (default) controls the retry ceiling

L24 vs L38:
  L24 Tool Synthesis  → Docker sandbox, explicit security, production-grade
  L38 @ai_function    → simpler API, rapid prototyping, trusted environments only

Package: strands-ai-functions (0.1.0)  →  module name: ai_functions
Model: OpenAIModel → LiteLLM proxy (localhost:4000) for consistency with the project

Usage:
    uv run python 11_platform/ai_functions.py
"""

import sys
import os

# This file is named ai_functions.py, which shadows the ai_functions package.
# Remove the script's own directory from sys.path so Python finds the installed
# package instead of this file when we do `from ai_functions import ...`.
_here = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p) != _here and p != ""]
sys.path.insert(0, os.path.dirname(_here))  # add project root

from pydantic import BaseModel
from ai_functions import ai_function, AIFunctionConfig, CodeExecutionMode, PostConditionResult
from strands.models.openai import OpenAIModel
from strands import Agent

# ---------------------------------------------------------------------------
# Shared model — LiteLLM proxy (same as rest of project)
# ---------------------------------------------------------------------------

model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
)

# ---------------------------------------------------------------------------
# ITERATION 1: Basic @ai_function — docstring as prompt
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 1: Basic @ai_function — docstring is the prompt")
print("=" * 70)
print("""
@ai_function wraps a regular Python function and intercepts its call.
Instead of running the function body, it:
  1. Substitutes {param_name} placeholders in the docstring
  2. Passes the rendered docstring as the prompt to a Strands Agent
  3. Forces the Agent to return output matching the return type annotation
  4. Returns the typed result to the caller

The function body is called first to get the prompt. If it returns None,
the docstring is used as the fallback template. This means you can write
complex prompt logic in the body or keep it simple with just a docstring.

Modes:
  DISABLED (default) → Agent uses structured output, no code execution
  LOCAL             → Agent gets a Python execution tool (smolagents AST)
""")


@ai_function(model=model)
def summarize(text: str, max_words: int) -> str:
    """Summarize the following text in at most {max_words} words:

{text}

Keep only the most important information."""


@ai_function(model=model)
def translate(text: str, target_language: str) -> str:
    """Translate the following text to {target_language}. Return only the translation.

{text}"""


print("--- summarize ---")
result = summarize(
    text=(
        "AWS AgentCore is a fully managed infrastructure for deploying and running "
        "AI agents at scale. It provides built-in long-term memory, session management, "
        "tool execution environments, and observability — removing the need for agents "
        "to manage their own state or infrastructure."
    ),
    max_words=20,
)
print(f"  {result!r}")

print("\n--- translate ---")
result = translate(text="The agent remembers your preferences.", target_language="French")
print(f"  {result!r}")


# ---------------------------------------------------------------------------
# ITERATION 2: Pydantic return type — structured output
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 2: Pydantic return type — structured output")
print("=" * 70)
print("""
Return type annotation controls the output schema.
When the return type is a Pydantic BaseModel, the Agent is forced to produce
a JSON payload matching that schema via structured_output_model.
No code execution needed — DISABLED mode works for any JSON-serializable type.

This is the equivalent of strands Agent(structured_output_model=MyModel)
but with none of the boilerplate.
""")


class SentimentResult(BaseModel):
    sentiment: str           # "positive" | "negative" | "neutral"
    score: float             # -1.0 (most negative) to 1.0 (most positive)
    key_phrases: list[str]   # 2-3 phrases that drove the sentiment


@ai_function(model=model)
def analyze_sentiment(review: str) -> SentimentResult:
    """Analyze the sentiment of this customer review:

{review}

Return the overall sentiment, a score from -1.0 to 1.0, and 2-3 key phrases
that most influenced the sentiment."""


print("--- positive review ---")
result = analyze_sentiment(
    review="Absolutely love this product! The build quality is exceptional and it arrived faster than expected."
)
print(f"  sentiment: {result.sentiment!r}")
print(f"  score:     {result.score:.2f}")
print(f"  phrases:   {result.key_phrases}")

print("\n--- negative review ---")
result = analyze_sentiment(
    review="Terrible experience. The item broke after two days and customer support was unhelpful."
)
print(f"  sentiment: {result.sentiment!r}")
print(f"  score:     {result.score:.2f}")
print(f"  phrases:   {result.key_phrases}")


# ---------------------------------------------------------------------------
# ITERATION 3: post_conditions — validation + auto-retry
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 3: post_conditions — validation with auto-retry")
print("=" * 70)
print("""
post_conditions are validation functions that run after each attempt.
Signature: (result) -> PostConditionResult | None
  Return None (or PostConditionResult(passed=True)) → passed
  Return PostConditionResult(passed=False, message="...") → retry

On failure, the error message is appended to the conversation as a user
turn and the agent is given another chance (up to max_attempts retries).
The conversation history is preserved across retries so the agent learns
from its mistakes.

Validators can also receive original input kwargs by accepting **kwargs.
""")


def has_three_lines(result: str) -> PostConditionResult | None:
    """Validate that result has exactly 3 lines (haiku structure)."""
    lines = [line.strip() for line in result.strip().split("\n") if line.strip()]
    if len(lines) == 3:
        return None  # passed
    return PostConditionResult(
        passed=False,
        message=f"Expected exactly 3 lines, got {len(lines)}. A haiku must have 3 lines.",
    )


def no_title_line(result: str) -> PostConditionResult | None:
    """Validate that result does not contain a title prefix like 'Haiku:'."""
    if ":" in result.split("\n")[0]:
        return PostConditionResult(
            passed=False,
            message="Do not include a title or label. Return only the three haiku lines.",
        )
    return None


@ai_function(
    model=model,
    post_conditions=[has_three_lines, no_title_line],
    max_attempts=3,
)
def write_haiku(topic: str) -> str:
    """Write a haiku (5-7-5 syllable pattern) about: {topic}

Return ONLY the three lines of the haiku. No title, no label, no explanation."""


print("--- write_haiku: mountains ---")
result = write_haiku(topic="mountains at dawn")
print(f"  Result:")
for line in result.strip().split("\n"):
    print(f"    {line}")

print("\n--- write_haiku: code ---")
result = write_haiku(topic="debugging code at midnight")
print(f"  Result:")
for line in result.strip().split("\n"):
    print(f"    {line}")


# ---------------------------------------------------------------------------
# ITERATION 4: CodeExecutionMode.LOCAL — agent writes and executes Python
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 4: CodeExecutionMode.LOCAL — agent-generated code execution")
print("=" * 70)
print("""
LOCAL mode gives the agent a python_executor tool backed by smolagents'
AST-based interpreter. The agent:
  1. Writes Python code to solve the problem
  2. Calls python_executor(code) to run it
  3. Reads stdout/stderr and iterates until correct
  4. Calls final_answer(result) to return the typed result

This is safer than eval/exec — smolagents uses an AST interpreter
with an allowlist of permitted imports. Use code_executor_additional_imports
to extend the allowlist beyond the defaults.

The function parameters are injected as variables in the execution namespace,
so the agent can reference them directly in its code.

Return type must be Pydantic model when using LOCAL mode (final_answer
signature is derived from it).
""")


class StatsResult(BaseModel):
    mean: float
    median: float
    std_dev: float
    minimum: float
    maximum: float


@ai_function(
    model=model,
    code_execution_mode=CodeExecutionMode.LOCAL,
    code_executor_additional_imports=["statistics"],
)
def compute_stats(numbers: list[float]) -> StatsResult:
    """Compute descriptive statistics for the list of numbers: {numbers}

Use Python's statistics module. Calculate mean, median, std_dev, minimum,
and maximum. Return the result using final_answer."""


print("--- compute_stats ---")
result = compute_stats(numbers=[4.2, 7.1, 2.8, 9.3, 5.5, 1.1, 8.7, 3.4, 6.6, 4.9])
print(f"  mean:    {result.mean:.3f}")
print(f"  median:  {result.median:.3f}")
print(f"  std_dev: {result.std_dev:.3f}")
print(f"  min:     {result.minimum:.3f}")
print(f"  max:     {result.maximum:.3f}")


# ---------------------------------------------------------------------------
# ITERATION 5: @ai_function as a Strands tool
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 5: @ai_function as a Strands tool")
print("=" * 70)
print("""
AIFunction implements ToolProvider — it can be passed directly to Agent(tools=[...]).
The parent agent can call it like any other tool. This enables:
  - Multi-step pipelines where each step is an @ai_function
  - A coordinator agent that delegates subtasks to specialized @ai_functions
  - Nesting: @ai_function tools can themselves have post_conditions + retries

When the parent agent calls the tool:
  tool_spec is derived from the function's name, docstring, and parameter annotations
  The tool's output is the typed result of the @ai_function
""")


@ai_function(model=model)
def extract_keywords(text: str) -> list[str]:
    """Extract the 5 most important keywords from this text:

{text}

Return as a JSON array of strings."""


@ai_function(model=model)
def generate_title(keywords: list[str], tone: str) -> str:
    """Generate a compelling blog post title using these keywords: {keywords}

The title should have a {tone} tone. Return only the title, no quotes."""


print("--- parent agent using @ai_functions as tools ---")
parent_agent = Agent(
    model=model,
    tools=[extract_keywords, generate_title],
    system_prompt="You are a content planning assistant. Use the available tools to help with content creation tasks.",
    callback_handler=None,
)

result = parent_agent(
    "I need a blog post title about machine learning in healthcare. "
    "First extract keywords from this description: 'AI models are revolutionizing medical diagnosis "
    "by analyzing patient data to detect cancer, predict outcomes, and personalize treatments.' "
    "Then use those keywords to generate an engaging title with a professional tone."
)
print(f"  {result}")


# ---------------------------------------------------------------------------
# ITERATION 6: Dynamic prompt from function body
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 6: Dynamic prompt from function body")
print("=" * 70)
print("""
The function body is called FIRST to produce the prompt.
If it returns a str, that string IS the prompt — the docstring is ignored.
If it returns None, the docstring with {param} substitution is the fallback.

This lets you write conditional prompt logic in Python:
  - switch prompt style based on input length or type
  - include/exclude sections based on flags
  - build prompts from data structures the docstring can't express

The docstring is then just documentation for the tool spec
(used by parent agents to understand what the function does).
""")


@ai_function(model=model)
def grade_answer(question: str, answer: str, difficulty: str) -> str:
    """Grade a student answer to a question."""
    # Dynamic prompt: adjust rubric depth based on difficulty
    if difficulty == "easy":
        rubric = "Is the core concept correct? A simple yes/no with brief justification."
    elif difficulty == "hard":
        rubric = (
            "Evaluate: (1) technical accuracy, (2) completeness, "
            "(3) use of precise terminology, (4) any missing nuance. "
            "Give a letter grade A-F with detailed reasoning."
        )
    else:
        rubric = "Is the answer mostly correct? Give a grade (A/B/C/D/F) and one sentence of feedback."

    return (
        f"Question: {question}\n\n"
        f"Student answer: {answer}\n\n"
        f"Grading rubric ({difficulty} difficulty): {rubric}"
    )


print("--- grade easy question ---")
result = grade_answer(
    question="What is a Python list?",
    answer="A collection of items.",
    difficulty="easy",
)
print(f"  {result}")

print("\n--- grade hard question ---")
result = grade_answer(
    question="Explain the difference between concurrency and parallelism in Python.",
    answer="Concurrency is when tasks overlap in time using async/await. Parallelism is true simultaneous execution using multiprocessing.",
    difficulty="hard",
)
print(f"  {result}")


# ---------------------------------------------------------------------------
# ITERATION 7: AI-powered post_condition
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 7: AI-powered post_condition — LLM validates LLM output")
print("=" * 70)
print("""
post_conditions can be @ai_function decorated functions.
The validator itself calls an LLM to evaluate the primary function's output.

Use case: semantic correctness checks that can't be expressed as code.
  - "Does this summary accurately reflect the source text?"
  - "Is this response free of harmful content?"
  - "Does this code solution actually solve the stated problem?"

The validator receives the result as its first argument, and can also
receive the original input kwargs by accepting **kwargs.

PostConditionResult(passed=False, message="...") from the validator
triggers retry with the message appended to the conversation.
""")


# The LLM judge: explicit named params so inspect.Signature.bind
# doesn't fold source into the **kwargs dict under the key "kwargs".
@ai_function(model=model)
def _consistency_judge(summary: str, source: str) -> PostConditionResult:
    """You are a fact-checking validator.

Original text:
{source}

Summary to check:
{summary}

Does the summary contain ONLY information present in the original text?
No invented facts, no hallucinations, no contradictions.
If accurate: return PostConditionResult(passed=True).
If inaccurate: return PostConditionResult(passed=False, message="<what is wrong>")."""


def check_factual_consistency(result: str, **kwargs) -> PostConditionResult | None:
    """Regular wrapper: pulls source from parent's bound_args and calls the LLM judge.

    PostConditionRunner calls this as check_factual_consistency(result, **parent_bound_args).
    We capture source from kwargs and forward it to the @ai_function judge with an
    explicit parameter — avoiding the inspect.Signature.bind **kwargs folding issue.
    """
    source = kwargs.get("source", "")
    if not source:
        return None  # can't validate without source text — pass through
    return _consistency_judge(summary=result, source=source)


SOURCE_TEXT = (
    "The Apollo 11 mission landed on the Moon on July 20, 1969. "
    "Neil Armstrong was the first person to walk on the lunar surface, "
    "followed by Buzz Aldrin. Michael Collins remained in orbit aboard "
    "the Command Module. The mission returned safely to Earth on July 24, 1969."
)


@ai_function(
    model=model,
    post_conditions=[check_factual_consistency],
    max_attempts=3,
)
def summarize_accurately(source: str, max_words: int) -> str:
    """Summarize the following text in at most {max_words} words:

{source}"""


print("--- summarize with factual consistency validator ---")
result = summarize_accurately(source=SOURCE_TEXT, max_words=25)
print(f"  {result}")

print("\n--- Summary ---")
print("  Iteration 6: Function body returns computed prompt string.")
print("  Iteration 7: @ai_function as a post_condition — LLM validates LLM output.")
print("  Both patterns are composable with all other @ai_function features.")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("L38 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Package
   • pip: strands-ai-functions  →  import: ai_functions
   • Dep: smolagents (for LOCAL mode AST executor)

2. @ai_function modes
   • DISABLED (default) → structured output from LLM; any JSON-serializable return type
   • LOCAL             → agent writes Python code, executes via smolagents AST
   • LOCAL requires Pydantic return type (final_answer signature derived from it)

3. Prompt building
   • Docstring with {param_name} is the primary prompt source
   • Function body can return a str for dynamic prompts; None falls back to docstring
   • Dynamic body: branch on inputs, build prompts from data structures
   • Params are injected into the execution namespace in LOCAL mode

4. post_conditions
   • Signature: (result) -> PostConditionResult | None
   • Return None or PostConditionResult(passed=True) to pass
   • Return PostConditionResult(passed=False, message="...") to trigger retry
   • Failure appends error to conversation — agent sees its mistake and corrects
   • max_attempts=10 default; each attempt shares conversation history
   • post_conditions can themselves be @ai_function — LLM validates LLM output
   • Validator receives original input kwargs via **kwargs parameter

5. AIFunction as a tool
   • Implements ToolProvider → pass to Agent(tools=[my_ai_func])
   • Tool spec derived from function name + docstring + param annotations
   • Enables pipeline architectures: coordinator agent → specialized @ai_functions

6. model=
   • None → Strands Agent default (Bedrock from env)
   • str → Bedrock model ID string
   • Model object → any strands Model (OpenAIModel, BedrockModel, etc.)

7. L38 vs L24 (Tool Synthesis)
   • L24: Docker sandbox, explicit security boundaries, production-hardened
   • L38: Simpler API, AST interpreter (not subprocess), trusted environments only
   • L38 is rapid prototyping; L24 is production code execution
""")
