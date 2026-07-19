"""
Probe: iter2 tool use in isolation with 30s timeout.
Test if transcript appears after two tool calls within 30s.
"""
import os
import asyncio, base64, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strands import tool
from strands.experimental.bidi import BidiAgent, BidiAudioInputEvent, BidiTranscriptStreamEvent
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

CHUNK = base64.b64encode(bytes(3200)).decode()

@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b

@tool
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

async def main():
    model = BidiNovaSonicModel(
        client_config={"boto_session": boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))}
    )
    question = "Add 37 and 45."  # single tool call — simpler
    print(f"[USER]: {question}")

    try:
        async with asyncio.timeout(30):
            async with BidiAgent(
                model=model,
                tools=[add_numbers, multiply_numbers],
                system_prompt="You are a math assistant. Use tools. One sentence answer.",
            ) as agent:
                for _ in range(3):
                    await agent.send(BidiAudioInputEvent(audio=CHUNK, format="pcm", sample_rate=16000, channels=1))
                    await asyncio.sleep(0.05)
                await agent.send(question)

                count = 0
                async for event in agent.receive():
                    ev = type(event).__name__
                    count += 1
                    if isinstance(event, BidiTranscriptStreamEvent) and event.role == "assistant":
                        print(f"  [ASSISTANT] ({count} events): {event.text}")
                        break
                    else:
                        print(f"  [{count:02d}] {ev}")
                    if count > 40:
                        print("  [TOO MANY EVENTS]")
                        break
    except asyncio.TimeoutError:
        print("[OUTER TIMEOUT 30s]")

asyncio.run(main())
