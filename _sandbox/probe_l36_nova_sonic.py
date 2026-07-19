"""
Probe: BidiNovaSonicModel internals + can we use text-only mode?
"""
import inspect, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel

print("=== BidiNovaSonicModel full source ===")
src = inspect.getsource(BidiNovaSonicModel)
print(src[:5000])
print("\n... [first 5000 chars shown]")

print("\n=== BidiNovaSonicModel methods ===")
methods = [m for m in dir(BidiNovaSonicModel) if not m.startswith("_")]
for m in methods:
    try:
        sig = inspect.signature(getattr(BidiNovaSonicModel, m))
        print(f"  {m}: {sig}")
    except Exception:
        print(f"  {m}: (not inspectable)")

# --- Check if model supports text input (vs audio-only) ---
print("\n=== BidiModel base class ===")
from strands.experimental.bidi.models.model import BidiModel
print(inspect.getsource(BidiModel)[:2000])
