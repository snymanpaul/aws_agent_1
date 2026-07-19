"""
Probe: Nova Sonic with continuous silent audio keepalive.
Nova Sonic is a continuous streaming model — audio must flow to keep the
connection alive. Send silent audio every ~200ms while waiting for response.
"""
import os
import asyncio, base64, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import (
    BidiAgent, BidiAudioInputEvent,
    BidiTranscriptStreamEvent, BidiResponseCompleteEvent,
    BidiConnectionStartEvent, BidiUsageEvent, BidiErrorEvent,
    BidiResponseStartEvent,
)
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

# 200ms of silence at 16kHz, 16-bit, mono = 6400 bytes
CHUNK_SAMPLES = 3200   # 100ms worth at 16kHz
SILENT_CHUNK = base64.b64encode(bytes(CHUNK_SAMPLES * 2)).decode()

async def send_silent_audio_loop(agent: BidiAgent, stop_event: asyncio.Event) -> None:
    """Keep sending silent audio chunks until stop_event is set."""
    while not stop_event.is_set():
        await agent.send(BidiAudioInputEvent(
            audio=SILENT_CHUNK,
            format="pcm",
            sample_rate=16000,
            channels=1,
        ))
        await asyncio.sleep(0.1)

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(client_config={"boto_session": boto_session})

    stop_audio = asyncio.Event()
    audio_task = None

    async with BidiAgent(
        model=model,
        system_prompt="You are a concise assistant. Reply in 1 sentence.",
    ) as agent:
        print("Agent started. Starting silent audio stream...")

        # Start continuous audio keepalive in background
        audio_task = asyncio.create_task(send_silent_audio_loop(agent, stop_audio))

        # Give audio stream time to establish
        await asyncio.sleep(0.3)

        # Send text question
        question = "What is 2 + 2?"
        print(f"[USER TEXT]: {question}")
        await agent.send(question)

        # Collect response events
        async for event in agent.receive():
            event_type = type(event).__name__
            if isinstance(event, BidiTranscriptStreamEvent) and event.is_final:
                print(f"[{event.role.upper()} TRANSCRIPT]: {event.current_transcript}")
            elif isinstance(event, BidiResponseCompleteEvent):
                print(f"[COMPLETE] stop_reason={event.stop_reason}")
                stop_audio.set()
                break
            elif isinstance(event, BidiConnectionStartEvent):
                print(f"[CONNECTED] model={event.model}")
            elif isinstance(event, BidiUsageEvent) and event.output_tokens > 0:
                print(f"[USAGE] out={event.output_tokens}")
            elif isinstance(event, BidiErrorEvent):
                print(f"[ERROR] {event.error}")
                stop_audio.set()
                break
            elif isinstance(event, BidiResponseStartEvent):
                print(f"[RESPONSE STARTING] id={event.response_id}")

    if audio_task and not audio_task.done():
        audio_task.cancel()
        try:
            await audio_task
        except asyncio.CancelledError:
            pass

    print("Done.")

asyncio.run(main())
