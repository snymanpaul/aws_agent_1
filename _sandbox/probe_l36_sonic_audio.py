"""
Probe: Nova Sonic with silent audio to satisfy audio stream requirement.
Also checks Python version constraint (docs say 3.12+, we run 3.13).
"""
import os
import sys
print(f"Python: {sys.version}")
# Docs note: BidiNovaSonicModel is only supported for Python 3.12+
# We're on 3.13 — should be fine (3.13 > 3.12)

import asyncio, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import (
    BidiAgent, BidiAudioInputEvent,
    BidiTranscriptStreamEvent, BidiResponseCompleteEvent,
    BidiConnectionStartEvent, BidiUsageEvent, BidiErrorEvent,
)
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

# Generate 200ms of silence at 16kHz, 16-bit, mono
# 16000 samples/sec * 0.2 sec * 2 bytes/sample = 6400 bytes
SILENT_PCM = bytes(6400)
SILENT_B64 = base64.b64encode(SILENT_PCM).decode()

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(
        client_config={"boto_session": boto_session},
    )

    async with BidiAgent(
        model=model,
        system_prompt="You are a concise assistant. Reply in 1 sentence.",
    ) as agent:
        print("Agent started")

        # First send silent audio to establish audio stream
        print("Sending silent audio...")
        await agent.send(BidiAudioInputEvent(
            audio=SILENT_B64,
            format="pcm",
            sample_rate=16000,
            channels=1,
        ))

        # Then send text
        print("Sending text: What is 2 + 2?")
        await agent.send("What is 2 + 2?")

        # Receive response
        async for event in agent.receive():
            event_type = type(event).__name__
            if isinstance(event, BidiTranscriptStreamEvent):
                if event.is_final:
                    print(f"[{event.role.upper()}]: {event.current_transcript}")
            elif isinstance(event, BidiResponseCompleteEvent):
                print(f"[COMPLETE] stop_reason={event.stop_reason}")
                break
            elif isinstance(event, BidiConnectionStartEvent):
                print(f"[CONNECTED] {event.connection_id}")
            elif isinstance(event, BidiUsageEvent):
                print(f"[USAGE] in={event.input_tokens} out={event.output_tokens}")
            elif isinstance(event, BidiErrorEvent):
                print(f"[ERROR] {event.error}")
                break
            else:
                print(f"[EVENT] {event_type}")

asyncio.run(main())
