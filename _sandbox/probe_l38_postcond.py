"""
Probe L38: How PostConditionRunner._check_condition passes kwargs.
- Read _check_condition full source
- Check if AIFunction.__signature__ is correctly detected for **kwargs
- Verify bound_args are passed when **kwargs present
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Remove script dir shadow
_here = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p) != _here and p != ""]
sys.path.insert(0, os.path.dirname(_here))

from ai_functions.core import AIFunction, PostConditionRunner
from ai_functions import ai_function, PostConditionResult

# --- 1. Full PostConditionRunner source ---
print("=== PostConditionRunner full source ===")
src = inspect.getsource(PostConditionRunner)
for i, line in enumerate(src.split("\n"), 1):
    print(f"  {i:3}: {line}")

# --- 2. Does inspect.signature on AIFunction show **kwargs? ---
print("\n=== inspect.signature on AIFunction with **kwargs func ===")

@ai_function
def my_validator(result: str, **kwargs) -> PostConditionResult:
    """Validate: {result}"""

print(f"  signature: {inspect.signature(my_validator)}")
params = inspect.signature(my_validator).parameters
for name, p in params.items():
    print(f"  param {name!r}: kind={p.kind.name}")
has_var_kw = any(
    p.kind == inspect.Parameter.VAR_KEYWORD
    for p in params.values()
)
print(f"  has VAR_KEYWORD (**kwargs): {has_var_kw}")
