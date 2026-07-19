"""
Probe: Nova Sonic v2 — capture response window precisely.
Strategy: burst of audio + text → stop audio → collect all events for 8s → stop.
We know v2 responds with audio. Check if BidiResponseCompleteEvent ever fires.
Print all event types.
"""
import os
import asyncio, base64, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import BidiAgent, BidiAudioInputEvent
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

CHUNK = base64.b64encode(bytes(3200)).decode()  # 100ms silence, 16kHz 16-bit mono

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(
        model_id="amazon.nova-2-sonic-v1:0",
        client_config={"boto_session": boto_session},
    )

    async with BidiAgent(
        model=model,
        system_prompt="You are a concise assistant. Reply in 1 sentence.",
    ) as agent:
        # Send 3 audio chunks (~300ms) to establish stream, then text
        for _ in range(3):
            await agent.send(BidiAudioInputEvent(audio=CHUNK, format="pcm", sample_rate=16000, channels=1))
            await asyncio.sleep(0.05)

        await agent.send("What is 2 + 2?")
        print("[USER]: What is 2 + 2?")

        # Collect all events for up to 8 seconds
        events_by_type = {}
        count = 0
        try:
            async with asyncio.timeout(8):
                async for event in agent.receive():
                    count += 1
                    ev_type = type(event).__name__
                    events_by_type[ev_type] = events_by_type.get(ev_type, 0) + 1
                    # Print non-usage events fully
                    if ev_type not in ("BidiUsageEvent", "BidiAudioStreamEvent"):
                        print(f"  [{count:02d}] {ev_type}: {vars(event)}")
                    else:
                        print(f"  [{count:02d}] {ev_type} (suppressed)")
        except asyncio.TimeoutError:
            print(f"\n[TIMEOUT at 8s]")
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {str(e)[:200]}")

    print(f"\nEvent summary (total={count}):")
    for t, n in sorted(events_by_type.items()):
        print(f"  {t}: {n}")

asyncio.run(main())
