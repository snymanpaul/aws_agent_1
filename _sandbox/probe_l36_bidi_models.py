"""
Probe: BidiModel constructors, IO module, and text-only demo feasibility.
"""
import inspect, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- 1. Model constructors via their actual modules ---
print("=== BidiNovaSonicModel ===")
try:
    from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
    print(f"  __init__: {inspect.signature(BidiNovaSonicModel.__init__)}")
    src = inspect.getsource(BidiNovaSonicModel.__init__)
    print(src[:1000])
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== BidiOpenAIRealtimeModel ===")
try:
    from strands.experimental.bidi.models.openai_realtime import BidiOpenAIRealtimeModel
    print(f"  __init__: {inspect.signature(BidiOpenAIRealtimeModel.__init__)}")
    src = inspect.getsource(BidiOpenAIRealtimeModel.__init__)
    print(src[:500])
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== GeminiLiveModel ===")
try:
    from strands.experimental.bidi.models.gemini_live import BidiGeminiLiveModel
    print(f"  __init__: {inspect.signature(BidiGeminiLiveModel.__init__)}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 2. IO module ---
print("\n=== strands.experimental.bidi.io module ===")
try:
    import strands.experimental.bidi.io as io_mod
    print(f"  exports: {dir(io_mod)}")
    for name in dir(io_mod):
        if not name.startswith("_"):
            obj = getattr(io_mod, name)
            if inspect.isclass(obj):
                try:
                    print(f"  {name}: {inspect.signature(obj.__init__)}")
                    # get source without pyaudio dependency crashing
                    try:
                        src = inspect.getsource(obj)
                        print(src[:800])
                    except Exception:
                        pass
                except Exception as ex:
                    print(f"  {name}: {ex}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 3. Check what BidiInput / BidiOutput callable interfaces look like ---
print("\n=== types.io ===")
try:
    from strands.experimental.bidi.types.io import BidiInput, BidiOutput
    print(f"  BidiInput: {inspect.getsource(BidiInput)}")
    print(f"  BidiOutput: {inspect.getsource(BidiOutput)}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 4. stop_conversation tool ---
print("\n=== stop_conversation tool ===")
try:
    from strands.experimental.bidi.tools.stop_conversation import stop_conversation
    print(f"  signature: {inspect.signature(stop_conversation)}")
    print(inspect.getsource(stop_conversation))
except Exception as e:
    print(f"  ERROR: {e}")

# --- 5. Text event types in detail ---
print("\n=== BidiTranscriptStreamEvent ===")
try:
    from strands.experimental.bidi import BidiTranscriptStreamEvent, BidiResponseCompleteEvent
    print(f"  TranscriptStream: {inspect.signature(BidiTranscriptStreamEvent.__init__)}")
    print(f"  ResponseComplete: {inspect.signature(BidiResponseCompleteEvent.__init__)}")
    # check if there's a text field we can easily read
    src = inspect.getsource(BidiTranscriptStreamEvent)
    print(src[:400])
except Exception as e:
    print(f"  ERROR: {e}")
