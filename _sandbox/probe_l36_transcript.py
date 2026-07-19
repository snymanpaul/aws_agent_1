"""
Probe: capture BidiTranscriptStreamEvent fields, find response completion signal.
"""
import os
import asyncio, base64, sys, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import (
    BidiAgent, BidiAudioInputEvent,
    BidiTranscriptStreamEvent, BidiResponseCompleteEvent,
    BidiResponseStartEvent, BidiConnectionStartEvent,
)
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

# Inspect BidiTranscriptStreamEvent fields
print("=== BidiTranscriptStreamEvent ===")
print("  __init__:", inspect.signature(BidiTranscriptStreamEvent.__init__))
# Check dataclass fields
try:
    import dataclasses
    print("  dataclass fields:", [f.name for f in dataclasses.fields(BidiTranscriptStreamEvent)])
except Exception:
    pass
# Check __slots__
if hasattr(BidiTranscriptStreamEvent, '__slots__'):
    print("  __slots__:", BidiTranscriptStreamEvent.__slots__)
# Check model_fields (pydantic)
if hasattr(BidiTranscriptStreamEvent, 'model_fields'):
    print("  model_fields:", list(BidiTranscriptStreamEvent.model_fields.keys()))

print("\n=== BidiResponseCompleteEvent source ===")
print(inspect.getsource(BidiResponseCompleteEvent))

# Check nova_sonic receive() for completionEvent handling
print("\n=== Nova Sonic receive() — how BidiResponseCompleteEvent is emitted ===")
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
src = inspect.getsource(BidiNovaSonicModel.receive)
print(src[:3000])

print("\n=== Nova Sonic _process_nova_event ===")
src2 = inspect.getsource(BidiNovaSonicModel._process_nova_event)
print(src2[:3000])

CHUNK = base64.b64encode(bytes(3200)).decode()

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(client_config={"boto_session": boto_session})

    async with BidiAgent(model=model, system_prompt="Reply in 1 sentence.") as agent:
        for _ in range(3):
            await agent.send(BidiAudioInputEvent(audio=CHUNK, format="pcm", sample_rate=16000, channels=1))
            await asyncio.sleep(0.05)
        await agent.send("What is 2 + 2?")

        try:
            async with asyncio.timeout(8):
                async for event in agent.receive():
                    if isinstance(event, BidiTranscriptStreamEvent):
                        # Direct attribute access
                        print(f"  TRANSCRIPT:"
                              f" role={event.role}"
                              f" is_final={event.is_final}"
                              f" text={repr(event.text[:60]) if event.text else None}"
                              f" current={repr(event.current_transcript[:60]) if event.current_transcript else None}")
                        if event.is_final and event.role == "assistant":
                            print(f"  >>> FINAL ASSISTANT TRANSCRIPT: {event.current_transcript}")
                            break
                    elif isinstance(event, BidiResponseCompleteEvent):
                        print(f"  COMPLETE: reason={event.stop_reason}")
                        break
        except asyncio.TimeoutError:
            print("  [TIMEOUT]")
        except Exception as e:
            print(f"  [ERROR] {e}")

asyncio.run(main())
