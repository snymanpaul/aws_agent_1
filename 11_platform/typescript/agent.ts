/**
 * L39: Strands Agents TypeScript SDK
 *
 * Demonstrates the key structural differences from the Python SDK:
 *   Tool input schema:  Zod schema objects  (vs Python type hints + docstring)
 *   Tool handler:       async function       (vs sync function with @tool decorator)
 *   Agent invocation:   agent.invoke(prompt) (vs agent(prompt))
 *   Lambda deployment:  native handler export pattern
 *
 * Feature gap vs Python SDK: A2A not supported, some advanced features pending parity.
 */

import { Agent, tool } from "@strands-agents/sdk";
import { OpenAIModel } from "@strands-agents/sdk/openai";
import { z } from "zod";

// ─── Model ───────────────────────────────────────────────────────────────────
// Use OpenAIModel with clientConfig.baseURL for LiteLLM (same pattern as Python SDK)
const model = new OpenAIModel({
  modelId: "claude-sonnet-4",
  apiKey: "sk-local",
  clientConfig: {
    baseURL: "http://localhost:4000",
  },
});

// ─── Tools (Zod schemas replace Python type hints + docstrings) ───────────────
const getWeather = tool({
  name: "get_weather",
  description: "Get current weather conditions for a city.",
  inputSchema: z.object({
    city: z.string().describe("City name, e.g. Seattle"),
    units: z.enum(["celsius", "fahrenheit"]).optional().describe("Temperature units"),
  }),
  callback: ({ city, units = "fahrenheit" }) => {
    // Stub — replace with real API call
    return `${city}: 72°${units === "celsius" ? "C" : "F"}, sunny`;
  },
});

const calculator = tool({
  name: "calculator",
  description: "Perform basic arithmetic: add, subtract, multiply, divide.",
  inputSchema: z.object({
    operation: z.enum(["add", "subtract", "multiply", "divide"]),
    a: z.number(),
    b: z.number(),
  }),
  callback: ({ operation, a, b }) => {
    switch (operation) {
      case "add": return a + b;
      case "subtract": return a - b;
      case "multiply": return a * b;
      case "divide":
        if (b === 0) return "Error: division by zero";
        return a / b;
    }
  },
});

// ─── Agent ────────────────────────────────────────────────────────────────────
const agent = new Agent({
  model,
  tools: [getWeather, calculator],
  systemPrompt: "You are a helpful assistant with weather and calculator tools. Be concise.",
  printer: false,  // suppress auto-print so we control output
});

// ─── Demo 1: invoke() — non-streaming, returns final AgentResult ───────────────
async function runInvoke() {
  console.log("\n=== invoke() demo ===");
  const result = await agent.invoke("What's the weather in Seattle? Also what is 42 * 17?");
  console.log(result.toString());
}

// ─── Demo 2: stream() — yields AgentStreamEvents for real-time output ──────────
async function runStream() {
  console.log("\n=== stream() demo ===");
  let textBuffer = "";

  for await (const event of agent.stream("What is 100 divided by 7? Round to 2 decimal places.")) {
    if (
      event.type === "modelStreamUpdateEvent" &&
      event.event.type === "modelContentBlockDeltaEvent" &&
      event.event.delta.type === "textDelta"
    ) {
      const chunk = event.event.delta.text;
      process.stdout.write(chunk);
      textBuffer += chunk;
    }
  }
  console.log(); // newline after streaming
}

// ─── Main ─────────────────────────────────────────────────────────────────────
await runInvoke();
await runStream();
