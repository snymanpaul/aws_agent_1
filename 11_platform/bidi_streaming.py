"""
Level 36: Bidirectional Streaming — Real-time Voice and Text Conversations
==========================================================================
Real-time bidirectional streaming via strands.experimental.bidi.
No microphone required: demonstrates the full API using silent audio +
text input, which is valid for Nova Sonic's stream protocol.

Key concepts:
  - BidiAgent: async context manager with start/send/receive/stop
  - BidiNovaSonicModel: AWS Nova Sonic — audio-primary, text also supported
  - Event-driven: AsyncGenerator of BidiOutputEvent subtypes
  - Audio stream protocol: 3 audio chunks needed to establish session,
    then send text or real audio
  - Break on BidiTranscriptStreamEvent(role='assistant') — text arrives
    before BidiResponseCompleteEvent (which waits for full audio to finish)

Nova Sonic vs BidiOpenAIRealtimeModel vs BidiGeminiLiveModel:
  Nova Sonic           → AWS Bedrock, audio-primary, no pyaudio needed for text
  OpenAIRealtimeModel  → OpenAI Realtime WebSocket API, gpt-realtime
  GeminiLiveModel      → Google Gemini Live, gemini-2.5-flash-native-audio-preview

I/O patterns:
  a) Manual: async with BidiAgent() as agent: send() + receive()
  b) IO protocol: BidiInput/BidiOutput callables → agent.run(inputs, outputs)
  c) Real audio: BidiAudioIO (requires pyaudio) → agent.run(...)

Extra package:
  pip install aws-sdk-bedrock-runtime   (for BidiNovaSonicModel)
  pip install pyaudio                   (for BidiAudioIO — NOT required here)

Usage:
    AWS_PROFILE=<your-sso-profile> uv run python 11_platform/bidi_streaming.py
"""

import asyncio
import base64
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import tool
from strands.experimental.bidi import (
    BidiAgent,
    BidiAudioInputEvent,
    BidiTranscriptStreamEvent,
    BidiResponseCompleteEvent,
    BidiResponseStartEvent,
    BidiConnectionStartEvent,
    BidiErrorEvent,
    BidiUsageEvent,
    BidiInterruptionEvent,
)
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
import boto3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 100ms of silence at 16kHz, 16-bit, mono (Nova Sonic default input format)
# Nova Sonic requires ≥3 chunks to establish a turn — pure text input times out.
SILENCE_CHUNK_100MS = base64.b64encode(bytes(3200)).decode()  # 100ms * 16000Hz * 2 bytes


def make_model() -> BidiNovaSonicModel:
    """Create Nova Sonic model with current AWS_PROFILE credentials."""
    boto_session = boto3.Session()  # picks up AWS_PROFILE from environment
    return BidiNovaSonicModel(client_config={"boto_session": boto_session})


async def send_audio_establish(agent: BidiAgent, chunks: int = 3) -> None:
    """Send N silent audio chunks to establish Nova Sonic's audio stream.

    Nova Sonic is audio-primary: it requires audio input to begin accepting
    a new turn. Without at least one audio event, sending text alone triggers
    a ValidationException: 'Timed out waiting for audio bytes'.

    This is not a hack — it mirrors what BidiAudioIO does with real microphone
    input. Silent chunks establish the connection so text input is processed.
    """
    for _ in range(chunks):
        await agent.send(BidiAudioInputEvent(
            audio=SILENCE_CHUNK_100MS,
            format="pcm",
            sample_rate=16000,
            channels=1,
        ))
        await asyncio.sleep(0.05)


async def receive_response(
    agent: BidiAgent,
    timeout: float = 15.0,
    stop_after_transcript: bool = True,
) -> dict:
    """Receive events until assistant transcript arrives or timeout.

    Break strategy:
      stop_after_transcript=True  → break on first role='assistant' transcript
        (text is ready; audio may still be streaming)
      stop_after_transcript=False → break on BidiResponseCompleteEvent
        (waits for all audio to finish — can take 10-20s)

    Returns dict with keys: transcript, audio_chunks, events_seen.
    """
    result = {"transcript": None, "audio_chunks": 0, "events_seen": []}

    try:
        async with asyncio.timeout(timeout):
            async for event in agent.receive():
                ev_type = type(event).__name__
                result["events_seen"].append(ev_type)

                if isinstance(event, BidiTranscriptStreamEvent):
                    if event.role == "assistant":
                        result["transcript"] = event.current_transcript or event.text
                        if stop_after_transcript:
                            break
                elif ev_type == "BidiAudioStreamEvent":
                    result["audio_chunks"] += 1
                elif isinstance(event, BidiResponseCompleteEvent):
                    result["transcript"] = result.get("transcript")
                    break
                elif isinstance(event, BidiErrorEvent):
                    result["error"] = str(event.error)
                    break

    except asyncio.TimeoutError:
        result["timeout"] = True

    return result


# ---------------------------------------------------------------------------
# Tools for Iteration 2
# ---------------------------------------------------------------------------

@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@tool
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together."""
    return a * b


# ---------------------------------------------------------------------------
# ITERATION 1: Basic text-to-text conversation
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 1: Basic bidirectional text conversation")
print("=" * 70)
print("""
BidiAgent is the async counterpart to Agent. Key differences:
  - Must be started with `await agent.start()` (or `async with BidiAgent() as agent:`)
  - Input is event-based: await agent.send("text") or BidiAudioInputEvent
  - Output is an async generator: async for event in agent.receive(): ...
  - Nova Sonic is audio-primary: 3 audio chunks needed to establish the turn

Event types:
  BidiConnectionStartEvent  — connection established (first event)
  BidiUsageEvent            — running token count (fires multiple times)
  BidiResponseStartEvent    — model started generating a new response
  BidiTranscriptStreamEvent — text content (user speech or assistant text)
  BidiAudioStreamEvent      — audio chunks for playback (role=assistant)
  BidiResponseCompleteEvent — all audio/text for this turn is done
  BidiInterruptionEvent     — user spoke while model was talking
  BidiErrorEvent            — connection or model error

Break signal: role='assistant' BidiTranscriptStreamEvent
  Text arrives before audio finishes — use this for text applications.
  BidiResponseCompleteEvent fires only after ALL audio is generated (slow).
""")


async def ask_one(
    question: str,
    system_prompt: str,
    tools: list | None = None,
    timeout: float = 20.0,
) -> dict:
    """Ask a single question with a fresh BidiAgent connection per call.

    Uses explicit start/stop (not `async with`) so we can impose a hard
    deadline on stop(). When we break out of receive() early (before
    BidiResponseCompleteEvent), Nova Sonic's audio stream is still open.
    agent.stop() can block waiting for the stream to drain — the 3s
    deadline forces past that instead of hanging the script.
    """
    agent = BidiAgent(
        model=make_model(),
        tools=tools or [],
        system_prompt=system_prompt,
    )
    result: dict = {}
    try:
        await agent.start()
        await send_audio_establish(agent, chunks=3)
        await agent.send(question)
        result = await receive_response(agent, timeout=timeout)
    finally:
        try:
            await asyncio.wait_for(agent.stop(), timeout=3.0)
        except (asyncio.TimeoutError, Exception):
            pass  # force past stuck cleanup — connection will close on GC
    return result


async def iter1_basic_conversation():
    sp = "You are a precise assistant. Keep responses to one short sentence."
    for question in [
        "What is 15 multiplied by 8?",
        "What is the capital of France?",
    ]:
        print(f"\n  [USER]: {question}")
        result = await ask_one(question, sp)
        transcript = result.get("transcript", "(no transcript)")
        print(f"  [ASSISTANT]: {transcript}")
        print(f"  (audio_chunks={result['audio_chunks']}, events={len(result['events_seen'])})")

print("--- running 2 questions ---")
asyncio.run(iter1_basic_conversation())


# ---------------------------------------------------------------------------
# ITERATION 2: Tools during streaming
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 2: Tools execute concurrently during voice streaming")
print("=" * 70)
print("""
BidiAgent supports tools identically to Agent — pass them at construction.
Tools execute concurrently with voice output: while the model speaks,
tool calls are queued and executed in parallel (ConcurrentToolExecutor).

Tool flow in events:
  BidiResponseStartEvent    — model starts generating
  ToolUseStreamEvent        — model is calling a tool
  ToolResultEvent           — tool finished; result sent back to model
  BidiTranscriptStreamEvent — model describes result via text/speech
  BidiResponseCompleteEvent — all done

The stop_conversation tool (built-in) ends the session gracefully.
""")


async def iter2_tool_use():
    # Single tool call — simpler, reliably completes in ~15s
    question = "What is 37 plus 45?"
    sp = (
        "You are a math assistant. Always use the provided tools to calculate. "
        "Keep responses to one short sentence showing the result."
    )
    print(f"\n  [USER]: {question}")
    result = await ask_one(question, sp, tools=[add_numbers, multiply_numbers], timeout=25.0)
    transcript = result.get("transcript", "(no transcript)")
    print(f"  [ASSISTANT]: {transcript}")
    tool_events = [e for e in result["events_seen"] if "Tool" in e]
    print(f"  (tool events: {tool_events})")

print("--- running tool-use question ---")
asyncio.run(iter2_tool_use())


# ---------------------------------------------------------------------------
# ITERATION 3: Event taxonomy reference
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("ITERATION 3: Event taxonomy and IO protocol")
print("=" * 70)
print("""
INPUT events (agent.send() accepts):
  str                             → converted to BidiTextInputEvent(text, role='user')
  BidiTextInputEvent(text, role)  → text message
  BidiAudioInputEvent(audio, format, sample_rate, channels)
    audio = base64-encoded PCM/WAV/OPUS/MP3
    format = 'pcm' | 'wav' | 'opus' | 'mp3'
    sample_rate = 16000 | 24000 | 48000
    channels = 1 | 2
  BidiImageInputEvent(image, mime_type)  → image (base64)

OUTPUT events (agent.receive() yields):
  BidiConnectionStartEvent(connection_id, model)
  BidiConnectionCloseEvent(connection_id, reason)
  BidiResponseStartEvent(response_id)
  BidiResponseCompleteEvent(response_id, stop_reason)
    stop_reason: 'complete' | 'interrupted' | 'error' | 'tool_use'
  BidiTranscriptStreamEvent(delta, text, role, is_final, current_transcript)
    role: 'user' (speech→text) | 'assistant' (response text)
  BidiAudioStreamEvent(audio, format, sample_rate, channels)  → playback
  BidiInterruptionEvent(reason)  → user speech detected while model was talking
  BidiUsageEvent(input_tokens, output_tokens, total_tokens)
  ToolUseStreamEvent, ToolResultEvent  → tool execution

IO PROTOCOL (agent.run() pattern):
  BidiInput protocol:
    async def start(agent) → None
    async def stop() → None
    def __call__() → Awaitable[BidiInputEvent]

  BidiOutput protocol:
    async def start(agent) → None
    async def stop() → None
    def __call__(event: BidiOutputEvent) → Awaitable[None]

  # Real audio (requires pyaudio):
  # audio_io = BidiAudioIO()
  # await agent.run(inputs=[audio_io.input()], outputs=[audio_io.output()])

MODELS:
  BidiNovaSonicModel(model_id, provider_config, client_config)
    model_id: 'amazon.nova-2-sonic-v1:0' (v2, default) or 'amazon.nova-sonic-v1:0' (v1)
    provider_config: {audio: {voice, input_rate, output_rate}, inference: {max_tokens, ...},
                      turn_detection: {endpointingSensitivity: HIGH|MEDIUM|LOW}}  # v2 only
    client_config: {boto_session: boto3.Session} or {region: 'us-east-1'}
    Requires: pip install aws-sdk-bedrock-runtime

  BidiOpenAIRealtimeModel(model_id='gpt-realtime', provider_config, client_config)
    Direct WebSocket to OpenAI Realtime API; client_config: {api_key: '...'}

  BidiGeminiLiveModel(model_id='gemini-2.5-flash-native-audio-preview-09-2025', ...)
    Google Gemini Live API
""")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 70)
print("L36 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Package
   • strands.experimental.bidi  (no extra pip install needed for text mode)
   • pip install aws-sdk-bedrock-runtime  (required for BidiNovaSonicModel)
   • pip install pyaudio  (required for BidiAudioIO mic/speaker I/O)

2. BidiAgent vs Agent
   • Agent: synchronous, request-response, agent(prompt) → result
   • BidiAgent: async, continuous streaming, send() + receive() events
   • BidiAgent: same tools, system_prompt, messages as Agent

3. Nova Sonic audio protocol
   • Audio-primary: 3+ BidiAudioInputEvent chunks required per turn
   • Without audio: ValidationException 'Timed out waiting for audio bytes'
   • Silent PCM works: 3 × 100ms silence chunks establish the turn
   • BidiTranscriptStreamEvent(role='assistant') carries text BEFORE audio ends

4. Break strategy
   • Do NOT wait for BidiResponseCompleteEvent (fires after all audio — slow)
   • Break on first BidiTranscriptStreamEvent(role='assistant') for text output
   • BidiResponseCompleteEvent is for audio playback completion tracking

5. Event taxonomy (input → model → output)
   BidiAudioInputEvent / BidiTextInputEvent → Nova Sonic →
   BidiConnectionStartEvent → BidiUsageEvent (x many) →
   BidiResponseStartEvent → BidiTranscriptStreamEvent + BidiAudioStreamEvent →
   BidiResponseCompleteEvent

6. IO protocol (agent.run() vs manual)
   Manual: async with BidiAgent() as agent: send() / receive()
   Protocol: BidiInput callable + BidiOutput callable → agent.run(inputs, outputs)
   Real audio: BidiAudioIO().input() + BidiAudioIO().output() → agent.run(...)

7. Tools in bidi
   • ConcurrentToolExecutor by default — tools run in parallel with audio
   • Tool events: ToolUseStreamEvent → ToolResultEvent → transcript follows
   • stop_conversation tool ends session (use 'stop conversation' phrase)

8. Providers
   Nova Sonic  → AWS Bedrock, SigV4 auth, us-east-1, audio-primary
   OpenAI      → WebSocket to OpenAI Realtime API, gpt-realtime
   Gemini Live → Google Gemini Live, gemini-2.5-flash-native-audio-preview
""")
