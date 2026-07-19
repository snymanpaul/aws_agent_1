"""Probe strands-agents-evals API surface."""
import importlib.metadata, inspect, pkgutil
import strands_evals as se

print(f"version: {importlib.metadata.version('strands-agents-evals')}")
print(f"top-level exports: {[x for x in dir(se) if not x.startswith('_')]}")

print("\n=== module tree ===")
for importer, modname, ispkg in pkgutil.walk_packages(
    path=se.__path__, prefix=se.__name__ + ".", onerror=lambda x: None
):
    print(f"  {modname}")

print("\n=== Experiment signature ===")
from strands_evals import Experiment
print(inspect.signature(Experiment.__init__))
print("methods:", [m for m in dir(Experiment) if not m.startswith("_")])

print("\n=== evaluators module ===")
try:
    from strands_evals import evaluators as ev
    names = [x for x in dir(ev) if not x.startswith("_") and x[0].isupper()]
    print(f"  classes: {names}")
    for name in names:
        cls = getattr(ev, name)
        try:
            sig = inspect.signature(cls.__init__)
            print(f"  {name}: {sig}")
        except Exception:
            pass
except Exception as e:
    print(f"  {e}")

print("\n=== generator module ===")
try:
    from strands_evals import generator as gen
    names = [x for x in dir(gen) if not x.startswith("_") and x[0].isupper()]
    print(f"  classes: {names}")
    for name in names:
        cls = getattr(gen, name)
        try:
            sig = inspect.signature(cls.__init__)
            print(f"  {name}: {sig}")
        except Exception:
            pass
except Exception as e:
    print(f"  {e}")
