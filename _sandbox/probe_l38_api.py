"""
Probe L38: Deep dive into ai_functions API.
Questions:
  1. CodeExecutionMode enum values
  2. PostConditionResult fields
  3. AIFunctionConfig full field defaults
  4. AIFunction.__call__ signature + docstring
  5. post_conditions function signature
  6. Source of core.py AIFunction.__call__ to understand the loop
  7. What model= accepts (str Bedrock ID vs Model object)
  8. LocalPythonExecutorTool — what imports are allowed by default?
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_functions import AIFunctionConfig, CodeExecutionMode, PostConditionResult, ai_function
from ai_functions.core import AIFunction, LocalPythonExecutorTool, PostConditionRunner
from ai_functions.validation.post_conditions import PostConditionResult as PCR

# --- 1. CodeExecutionMode values ---
print("=== CodeExecutionMode values ===")
for member in CodeExecutionMode:
    print(f"  {member.name} = {member.value!r}")

# --- 2. PostConditionResult schema ---
print("\n=== PostConditionResult schema ===")
try:
    print(f"  fields: {list(PostConditionResult.model_fields.keys())}")
    for name, field in PostConditionResult.model_fields.items():
        print(f"  {name}: {field.annotation} (default={field.default!r})")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. AIFunctionConfig defaults ---
print("\n=== AIFunctionConfig defaults ===")
cfg = AIFunctionConfig()
print(f"  model:                        {cfg.model!r}")
print(f"  system_prompt:                {cfg.system_prompt!r}")
print(f"  max_attempts:                 {cfg.max_attempts}")
print(f"  code_execution_mode:          {cfg.code_execution_mode!r}")
print(f"  post_conditions:              {cfg.post_conditions!r}")
print(f"  code_executor_additional_imports: {cfg.code_executor_additional_imports!r}")
print(f"  agent_kwargs:                 {cfg.agent_kwargs!r}")

# --- 4. AIFunction.__call__ signature ---
print("\n=== AIFunction.__call__ ===")
try:
    print(f"  signature: {inspect.signature(AIFunction.__call__)}")
    print(f"  docstring: {inspect.getdoc(AIFunction.__call__)}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. AIFunction source (key method) ---
print("\n=== AIFunction source (core.py key methods) ===")
try:
    src = inspect.getsource(AIFunction)
    # Print the first 200 lines
    lines = src.split("\n")
    for i, line in enumerate(lines[:200], 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 6. PostConditionRunner source ---
print("\n=== PostConditionRunner source ===")
try:
    src = inspect.getsource(PostConditionRunner)
    for i, line in enumerate(src.split("\n")[:80], 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 7. LocalPythonExecutorTool defaults ---
print("\n=== LocalPythonExecutorTool ===")
try:
    print(f"  signature: {inspect.signature(LocalPythonExecutorTool.__init__)}")
    src = inspect.getsource(LocalPythonExecutorTool)
    for i, line in enumerate(src.split("\n")[:60], 1):
        print(f"  {i:3}: {line}")
except Exception as e:
    print(f"  ERROR: {e}")
