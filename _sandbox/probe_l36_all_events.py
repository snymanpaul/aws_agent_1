"""
Probe: print ALL events from Nova Sonic with 15s timeout.
Goals:
  - See every event type that comes back
  - Understand why BidiResponseCompleteEvent never arrives
  - Does BidiTranscriptStreamEvent ever appear?
Strategy: burst of audio (1s) → text question → stop audio → wait 15s
"""
import os
import asyncio, base64, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import BidiAgent, BidiAudioInputEvent
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

# 100ms chunk of silence at 16kHz, 16-bit mono
CHUNK = base64.b64encode(bytes(3200)).decode()  # 100ms * 16000 * 2 bytes

async def recv_with_timeout(agent, timeout=15.0):
    """Receive all events with timeout, print everything."""
    count = 0
    try:
        async with asyncio.timeout(timeout):
            async for event in agent.receive():
                count += 1
                ev_type = type(event).__name__
                # Print all fields of the event
                fields = {k: v for k, v in vars(event).items() if not k.startswith('_')}
                # Truncate large values
                for k in fields:
                    if isinstance(fields[k], (str, bytes)) and len(str(fields[k])) > 80:
                        fields[k] = str(fields[k])[:80] + '...'
                print(f"  [{count:02d}] {ev_type}: {fields}")
    except asyncio.TimeoutError:
        print(f"  [TIMEOUT after {timeout}s — received {count} events]")
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(
        model_id="amazon.nova-sonic-v1:0",   # try v1 (no turn_detection complexity)
        client_config={"boto_session": boto_session},
    )

    async with BidiAgent(
        model=model,
        system_prompt="You are a concise assistant.",
    ) as agent:
        print("--- Sending 5 audio chunks (500ms silence) ---")
        for _ in range(5):
            await agent.send(BidiAudioInputEvent(
                audio=CHUNK, format="pcm", sample_rate=16000, channels=1,
            ))
            await asyncio.sleep(0.05)

        print("--- Sending text: What is 2 + 2? ---")
        await agent.send("What is 2 + 2?")

        print("--- Waiting for response (no more audio sent) ---")
        await recv_with_timeout(agent, timeout=15.0)

asyncio.run(main())
