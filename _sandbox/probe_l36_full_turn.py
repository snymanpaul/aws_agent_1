"""
Probe: full Nova Sonic turn with 20s timeout.
We know BidiResponseCompleteEvent fires on completionEnd (after all audio generated).
For a 1-sentence voice response, audio generation takes several seconds.
"""
import os
import asyncio, base64, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import (
    BidiAgent, BidiAudioInputEvent,
    BidiTranscriptStreamEvent, BidiResponseCompleteEvent,
    BidiResponseStartEvent, BidiConnectionStartEvent, BidiErrorEvent,
)
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

CHUNK = base64.b64encode(bytes(3200)).decode()  # 100ms silence

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(client_config={"boto_session": boto_session})

    async with BidiAgent(
        model=model,
        system_prompt="You are a concise assistant. Reply in exactly one short sentence.",
    ) as agent:
        # Send 3 audio chunks → text → stop audio
        for _ in range(3):
            await agent.send(BidiAudioInputEvent(audio=CHUNK, format="pcm", sample_rate=16000, channels=1))
            await asyncio.sleep(0.05)

        question = "What is 2 + 2?"
        print(f"[USER]: {question}")
        await agent.send(question)

        transcripts = []
        audio_count = 0
        event_log = []

        try:
            async with asyncio.timeout(20):
                async for event in agent.receive():
                    ev_type = type(event).__name__

                    if isinstance(event, BidiTranscriptStreamEvent):
                        transcripts.append({
                            "role": event.role,
                            "is_final": event.is_final,
                            "text": event.text,
                            "current": event.current_transcript,
                        })
                        print(f"  [TRANSCRIPT] role={event.role} final={event.is_final} text={repr(event.text[:80])}")
                    elif ev_type == "BidiAudioStreamEvent":
                        audio_count += 1
                    elif isinstance(event, BidiResponseCompleteEvent):
                        print(f"  [COMPLETE] reason={event.stop_reason}")
                        break
                    elif isinstance(event, BidiConnectionStartEvent):
                        print(f"  [CONNECTED] model={event.model}")
                    elif isinstance(event, BidiErrorEvent):
                        print(f"  [ERROR] {event.error}")
                        break
                    else:
                        print(f"  [EVENT] {ev_type}")

        except asyncio.TimeoutError:
            print(f"  [TIMEOUT at 20s] audio_chunks={audio_count}")
        except Exception as e:
            print(f"  [ERROR] {type(e).__name__}: {str(e)[:200]}")

        print(f"\nSummary: {audio_count} audio chunks, {len(transcripts)} transcripts")
        for t in transcripts:
            print(f"  [{t['role']}] final={t['is_final']}: {t['current']}")

asyncio.run(main())
