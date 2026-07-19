"""Probe Strands Evals SDK surface before writing L35."""
import importlib.metadata

try:
    print(f"strands version: {importlib.metadata.version('strands-agents')}")
except Exception as e:
    print(f"strands version: {e}")

# Check for evals extra
print("\n=== strands.evals ===")
try:
    import strands.evals as evals
    print(dir(evals))
except ImportError as e:
    print(f"  not available: {e}")

# Check for evaluation-related modules in strands
print("\n=== strands top-level ===")
import strands
items = [x for x in dir(strands) if any(k in x.lower() for k in ["eval", "experiment", "topic", "plan"])]
print(f"  {items}")

# Check strands.experimental
print("\n=== strands.experimental ===")
try:
    import strands.experimental as exp
    print(dir(exp))
    items = [x for x in dir(exp) if any(k in x.lower() for k in ["eval", "experiment"])]
    print(f"  eval-related: {items}")
except ImportError as e:
    print(f"  {e}")

# Check if there's a separate evals package
print("\n=== all strands-related installed packages ===")
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-m", "pip", "list"],
    capture_output=True, text=True
)
for line in result.stdout.splitlines():
    if "strands" in line.lower() or "eval" in line.lower():
        print(f"  {line}")

# Check strands.evals via importlib
print("\n=== importlib find strands.evals ===")
try:
    spec = importlib.util.find_spec("strands.evals")
    print(f"  strands.evals spec: {spec}")
except Exception as e:
    print(f"  {e}")
import importlib.util
try:
    spec = importlib.util.find_spec("strands_evals")
    print(f"  strands_evals spec: {spec}")
except Exception as e:
    print(f"  {e}")
