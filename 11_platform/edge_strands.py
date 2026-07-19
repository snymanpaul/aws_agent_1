"""
L40: Edge Strands + Cloud Orchestration

Two-tier agent architecture:
  Edge agent  — LlamaCppModel (Ollama/llama.cpp) — fast, local, cheap
  Cloud agent — Claude via LiteLLM              — complex reasoning, planning

The edge agent handles routine tasks locally. When it needs multi-step
reasoning or planning beyond its capability, it delegates to the cloud
agent via a `consult_cloud` tool and returns the result to the caller.

Real-world equivalent:
  Edge device (Jetson/Raspberry Pi) with a 3B SLM running at low latency
  Cloud (AgentCore/Bedrock) invoked only when the local model is stuck

IMPORTANT: All scenarios run inside a single asyncio.run(main()) to keep
the LlamaCppModel's httpx.AsyncClient on one event loop. consult_cloud is
async and calls cloud_agent.invoke_async() — no nested asyncio.run() calls.
"""

import asyncio
from strands import Agent, tool
from strands.models import LlamaCppModel
from strands.models.openai import OpenAIModel

# ─── Models ───────────────────────────────────────────────────────────────────

# Edge: local SLM via Ollama (simulates llama.cpp server on a Jetson/Pi)
# LlamaCppModel works with any OpenAI-compatible server at base_url
edge_model = LlamaCppModel(
    base_url="http://localhost:11434",   # Ollama endpoint (llama.cpp: port 8080)
    model_id="llama3.2:3b",
)

# Cloud: Claude Sonnet 4 via LiteLLM proxy
cloud_model = OpenAIModel(
    model_id="claude-sonnet-4",
    client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
)

# ─── Cloud agent (created first — referenced by the edge tool below) ───────────
cloud_agent = Agent(
    model=cloud_model,
    system_prompt=(
        "You are a cloud reasoning assistant. "
        "Provide concise, accurate answers. "
        "The edge device has limited context — be direct and specific."
    ),
    callback_handler=None,
)

# ─── Tools available to the edge agent ───────────────────────────────────────

@tool
def read_sensor(sensor_id: str) -> dict:
    """Read current value from a named edge sensor (temperature, humidity, motion)."""
    # Stub — on real hardware this would read GPIO / MQTT / I2C
    stubs = {
        "temperature": {"value": 23.4, "unit": "C"},
        "humidity":    {"value": 61.2, "unit": "%"},
        "motion":      {"detected": True, "confidence": 0.92},
    }
    return stubs.get(sensor_id, {"error": f"unknown sensor: {sensor_id}"})


@tool
def actuate(device: str, command: str) -> str:
    """Send a command to an edge actuator (fan, alarm, display)."""
    # Stub — on real hardware this would write GPIO / serial / MQTT
    return f"[ACTUATOR] {device} <- {command} (acknowledged)"


@tool
async def consult_cloud(question: str) -> str:
    """
    Delegate a question to the cloud reasoning agent when local reasoning
    is insufficient. Use for: multi-step planning, anomaly diagnosis,
    complex calculations, or any task requiring deep reasoning.
    """
    print(f"  [edge -> cloud] {question}")
    result = await cloud_agent.invoke_async(question)
    response = str(result)
    print(f"  [cloud -> edge] {response[:120]}...")
    return response


# ─── Edge agent ───────────────────────────────────────────────────────────────
edge_agent = Agent(
    model=edge_model,
    tools=[read_sensor, actuate, consult_cloud],
    system_prompt=(
        "You are an edge device agent with limited compute. "
        "Handle simple sensor reads and actuations locally. "
        "For complex reasoning, planning, or anomaly analysis — use consult_cloud. "
        "Be brief. Respond in 1-2 sentences."
    ),
    callback_handler=None,
)

async def main() -> None:
    # Scenario 1: local task — edge handles it without cloud
    print("=== Scenario 1: local sensor read + actuation ===")
    result = await edge_agent.invoke_async(
        "Read the temperature sensor and turn on the fan if it's above 22°C."
    )
    print(result)

    # Scenario 2: cloud delegation — edge detects complexity, delegates
    print("\n=== Scenario 2: cloud delegation for complex reasoning ===")
    result = await edge_agent.invoke_async(
        "Motion sensor detected something. Temperature is rising. "
        "Consult the cloud to diagnose what might be happening and recommend an action plan."
    )
    print(result)

    # Scenario 3: planning question — edge routes to cloud immediately
    print("\n=== Scenario 3: edge delegates a planning question to cloud ===")
    result = await edge_agent.invoke_async(
        "The humidity has been above 60% for 3 hours and temperature is 23.4°C. "
        "Ask the cloud whether this is within safe operating range for electronics "
        "and what corrective actions I should take."
    )
    print(result)


asyncio.run(main())
