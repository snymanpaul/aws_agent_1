"""
Probe L38: Execution loop + model config.
Questions:
  1. _execute_async source — how does retry work?
  2. Does model=None use env vars or default Bedrock?
  3. Can we pass an OpenAIModel (for LiteLLM proxy)?
  4. How does docstring template substitution work?
  5. What does DISABLED mode (structured output) look like in practice?
  6. Does @ai_function accept async functions?
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_functions.core import AIFunction
from ai_functions.utils._template import Template

# --- 1. _execute_async source ---
print("=== AIFunction._execute_async source ===")
try:
    src = inspect.getsource(AIFunction._execute_async)
    for i, line in enumerate(src.split("\n"), 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 2. Template substitution ---
print("\n=== Template substitution (docstring templating) ===")
try:
    print(f"  Template source excerpt:")
    src = inspect.getsource(Template)
    for i, line in enumerate(src.split("\n")[:40], 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. _build_prompt method ---
print("\n=== AIFunction._build_prompt ===")
try:
    src = inspect.getsource(AIFunction._build_prompt)
    for i, line in enumerate(src.split("\n"), 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. _create_agent method ---
print("\n=== AIFunction._create_agent ===")
try:
    src = inspect.getsource(AIFunction._create_agent)
    for i, line in enumerate(src.split("\n"), 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. Simple smoke test: DISABLED mode with a Pydantic return type ---
print("\n=== Smoke test: DISABLED mode + str return type (should fail) ===")
try:
    from ai_functions import ai_function, AIFunctionConfig, CodeExecutionMode

    @ai_function(code_execution_mode=CodeExecutionMode.DISABLED)
    def bad_func(x: str) -> str:  # str is not Pydantic — should raise ValueError
        """Return {x} but capitalized."""

    print("  No error raised — unexpected")
except ValueError as e:
    print(f"  Expected ValueError: {e}")
except Exception as e:
    print(f"  Unexpected error: {type(e).__name__}: {e}")

# --- 6. Check str return type in LOCAL mode (should work) ---
print("\n=== Smoke test: LOCAL mode + str return type ===")
try:
    from ai_functions import ai_function, CodeExecutionMode

    @ai_function(code_execution_mode=CodeExecutionMode.LOCAL)
    def good_func(x: str) -> str:
        """Return {x} but capitalized."""

    print(f"  Created: {type(good_func).__name__}")
    print(f"  is_structured_output_enabled: {good_func._is_structured_output_enabled}")
    print(f"  is_return_wrapped: {good_func._is_return_wrapped}")
    print(f"  return type: {good_func._return_type}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

# --- 7. Check DISABLED mode + Pydantic return (should work) ---
print("\n=== Smoke test: DISABLED mode + Pydantic return type ===")
try:
    from pydantic import BaseModel
    from ai_functions import ai_function, CodeExecutionMode

    class Answer(BaseModel):
        result: str
        confidence: float

    @ai_function(code_execution_mode=CodeExecutionMode.DISABLED)
    def pydantic_func(question: str) -> Answer:
        """Answer this question: {question}. Return as Answer model."""

    print(f"  Created: {type(pydantic_func).__name__}")
    print(f"  is_structured_output_enabled: {pydantic_func._is_structured_output_enabled}")
    print(f"  structured_output_type: {pydantic_func._structured_output_type}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

# --- 8. Does model= accept OpenAIModel? ---
print("\n=== model= accepts OpenAIModel? ===")
try:
    from strands.models.openai import OpenAIModel
    from ai_functions import ai_function

    oai_model = OpenAIModel(
        model_id="claude-sonnet-4",
        client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
    )

    @ai_function(model=oai_model)
    def model_test(x: str) -> str:
        """Return: {x}"""

    print(f"  Created with OpenAIModel: {type(model_test.config.model).__name__}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")
