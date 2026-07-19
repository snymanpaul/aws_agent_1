"""
Probe: minimal text-only BidiAgent loop with Nova Sonic.
Verify:
  1. async with BidiAgent() as agent: context manager works
  2. await agent.send("text") works
  3. async for event in agent.receive(): yields events
  4. BidiResponseCompleteEvent signals end of a turn
  5. What events actually come back for a text input
"""
import os
import asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi import (
    BidiAgent,
    BidiTranscriptStreamEvent,
    BidiResponseCompleteEvent,
    BidiConnectionStartEvent,
    BidiConnectionCloseEvent,
    BidiErrorEvent,
    BidiUsageEvent,
    BidiInterruptionEvent,
)
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel

import boto3

async def main():
    boto_session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))
    model = BidiNovaSonicModel(
        client_config={"boto_session": boto_session},
    )

    print("=== Starting BidiAgent text loop ===")
    async with BidiAgent(
        model=model,
        system_prompt="You are a concise assistant. Keep responses to 1-2 sentences.",
    ) as agent:
        print("  Agent started OK")

        # Send a text message
        print("\n[SENDING] What is 2 + 2?")
        await agent.send("What is 2 + 2?")

        # Receive events until response is complete
        final_text = ""
        event_count = 0
        async for event in agent.receive():
            event_count += 1
            event_type = type(event).__name__

            if isinstance(event, BidiTranscriptStreamEvent):
                if event.is_final and event.role == "assistant":
                    final_text = event.current_transcript or event.text
                    print(f"  [TRANSCRIPT final] role={event.role}: {final_text[:100]}")
                elif event.role == "assistant" and not event.is_final:
                    pass  # streaming delta, skip
            elif isinstance(event, BidiResponseCompleteEvent):
                print(f"  [RESPONSE COMPLETE] stop_reason={event.stop_reason}")
                break
            elif isinstance(event, BidiConnectionStartEvent):
                print(f"  [CONNECTION START] id={event.connection_id}, model={event.model}")
            elif isinstance(event, BidiUsageEvent):
                print(f"  [USAGE] in={event.input_tokens}, out={event.output_tokens}")
            elif isinstance(event, BidiErrorEvent):
                print(f"  [ERROR] {event.error}")
                break
            else:
                print(f"  [EVENT] {event_type}")

            if event_count > 50:
                print("  [STOPPING] too many events")
                break

        print(f"\nFinal answer: {final_text}")
        print(f"Events received: {event_count}")

asyncio.run(main())
