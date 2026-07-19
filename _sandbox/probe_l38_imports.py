"""
Probe: Does code_executor_additional_imports install missing packages or
       only allow already-installed ones?

Test: Authorize 'cowsay' (not installed in venv) and try to import it.
Expected: ImportError/ModuleNotFoundError if it only allows, no error if it installs.
"""
import sys
from smolagents.local_python_executor import LocalPythonExecutor

# Confirm cowsay is not installed
try:
    import cowsay  # type: ignore
    print("SKIP: cowsay is already installed — can't test this way")
    sys.exit(0)
except ImportError:
    print("Confirmed: cowsay is NOT installed in current venv")

# Create executor with cowsay in the authorized imports allowlist
executor = LocalPythonExecutor(
    additional_authorized_imports=["cowsay"],
    additional_functions={},
)
executor.send_tools({})

# Try to import cowsay inside the executor
code = """
import cowsay
print(cowsay.cow('hello'))
"""

print("\nRunning code with cowsay in additional_authorized_imports...")
try:
    output, error, _ = executor(code)
    print(f"stdout: {output!r}")
    print(f"error:  {error!r}")
    if error:
        print("\nResult: additional_authorized_imports does NOT install packages.")
        print("It only removes the import-blocked error — the underlying ModuleNotFoundError still fires.")
    else:
        print("\nResult: cowsay was available — unexpected (must already be installed somewhere).")
except Exception as e:
    print(f"Exception raised: {type(e).__name__}: {e}")
    print("\nResult: additional_authorized_imports does NOT install packages.")
