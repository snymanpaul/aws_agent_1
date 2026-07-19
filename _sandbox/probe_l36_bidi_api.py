"""
Probe: strands.experimental.bidi API surface.
Answer:
  1. Does strands.experimental.bidi exist in installed version?
  2. What classes/functions are exported?
  3. Signatures for BidiAgent, BidiNovaSonicModel, BidiAudioIO
  4. Is text-only mode available (no real microphone needed)?
  5. What I/O handler interface does BidiAgent expect?
  6. What does a minimal run loop look like?
"""
import importlib.metadata, inspect, pkgutil, sys, os

print(f"strands version: {importlib.metadata.version('strands-agents')}")

# --- 1. Check if strands.experimental exists ---
print("\n=== strands.experimental submodules ===")
try:
    import strands.experimental as exp
    print(f"  strands.experimental: {dir(exp)}")
    for importer, modname, ispkg in pkgutil.walk_packages(
        path=exp.__path__, prefix=exp.__name__ + ".", onerror=lambda x: None
    ):
        print(f"  {modname}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 2. Try importing bidi submodule ---
print("\n=== strands.experimental.bidi ===")
try:
    import strands.experimental.bidi as bidi
    names = [x for x in dir(bidi) if not x.startswith("_")]
    print(f"  exports: {names}")
    for importer, modname, ispkg in pkgutil.walk_packages(
        path=bidi.__path__, prefix=bidi.__name__ + ".", onerror=lambda x: None
    ):
        print(f"  {modname}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. Try specific known classes ---
print("\n=== BidiAgent ===")
try:
    from strands.experimental.bidi import BidiAgent
    print(f"  BidiAgent.__init__: {inspect.signature(BidiAgent.__init__)}")
    methods = [m for m in dir(BidiAgent) if not m.startswith("_") and callable(getattr(BidiAgent, m))]
    print(f"  methods: {methods}")
    try:
        print(inspect.getsource(BidiAgent))
    except Exception:
        print("  (source not available — likely compiled)")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== BidiNovaSonicModel ===")
try:
    from strands.experimental.bidi import BidiNovaSonicModel
    print(f"  __init__: {inspect.signature(BidiNovaSonicModel.__init__)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== BidiOpenAIRealtimeModel ===")
try:
    from strands.experimental.bidi import BidiOpenAIRealtimeModel
    print(f"  __init__: {inspect.signature(BidiOpenAIRealtimeModel.__init__)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== BidiGeminiLiveModel ===")
try:
    from strands.experimental.bidi import BidiGeminiLiveModel
    print(f"  __init__: {inspect.signature(BidiGeminiLiveModel.__init__)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== I/O handlers ===")
for cls_name in ["BidiAudioIO", "BidiTextIO", "BidiIO", "StdioIO", "ConsoleIO"]:
    try:
        mod = __import__(f"strands.experimental.bidi", fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        print(f"  {cls_name}: {inspect.signature(cls.__init__)}")
    except Exception as e:
        print(f"  {cls_name}: {e}")

# --- 4. Check if there's a text-mode input ---
print("\n=== Search for text input handlers ===")
try:
    import strands.experimental.bidi as bidi
    all_names = [x for x in dir(bidi) if not x.startswith("_")]
    print(f"  All exports: {all_names}")
    for name in all_names:
        obj = getattr(bidi, name)
        if inspect.isclass(obj):
            try:
                sig = inspect.signature(obj.__init__)
                print(f"  {name}: {sig}")
            except Exception:
                pass
except Exception as e:
    print(f"  {e}")
