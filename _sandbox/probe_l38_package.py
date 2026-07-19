"""
Probe L38: Explore strands-ai-functions package structure.
Questions:
  1. What modules/classes are exported from strands_ai_functions?
  2. What is the @ai_function decorator signature?
  3. What is the AIFunctionAgent / runner class?
  4. What code execution sandbox is used?
  5. What imports are available / restricted?
  6. How does auto-retry / validation work?
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_functions

# --- 1. Top-level exports ---
print("=== ai_functions top-level exports ===")
for name in sorted(dir(ai_functions)):
    if not name.startswith("__"):
        obj = getattr(ai_functions, name)
        print(f"  {name}: {type(obj).__name__}")

# --- 2. Package structure (files) ---
print("\n=== Package files ===")
pkg_dir = os.path.dirname(ai_functions.__file__)
for root, dirs, files in os.walk(pkg_dir):
    dirs[:] = [d for d in dirs if not d.startswith("__")]
    for f in sorted(files):
        if f.endswith(".py"):
            rel = os.path.relpath(os.path.join(root, f), pkg_dir)
            print(f"  {rel}")

# --- 3. ai_function decorator signature ---
print("\n=== ai_function decorator ===")
try:
    from ai_functions import ai_function
    print(f"  type: {type(ai_function).__name__}")
    print(f"  signature: {inspect.signature(ai_function)}")
    print(f"  docstring: {inspect.getdoc(ai_function)}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. Find the agent/runner class ---
print("\n=== Agent / Runner classes ===")
import pkgutil, importlib

for importer, modname, ispkg in pkgutil.walk_packages(
    path=[pkg_dir], prefix="ai_functions.", onerror=lambda x: None
):
    try:
        mod = importlib.import_module(modname)
        for name in dir(mod):
            obj = getattr(mod, name)
            if inspect.isclass(obj) and obj.__module__.startswith("ai_functions"):
                print(f"  {modname}.{name}")
                try:
                    print(f"    __init__: {inspect.signature(obj.__init__)}")
                except Exception:
                    pass
    except Exception as e:
        print(f"  {modname}: ERROR {e}")
