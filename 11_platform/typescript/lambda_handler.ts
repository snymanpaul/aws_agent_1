/**
 * L39: Lambda Handler Pattern
 *
 * Demonstrates the native Lambda export pattern for serverless deployment.
 * The agent is created once at module load (warm starts reuse it).
 *
 * Deploy pattern:
 *   - Bundle with esbuild: esbuild lambda_handler.ts --bundle --platform=node --target=node22 --outfile=dist/index.js
 *   - Lambda handler: index.handler
 *   - Runtime: Node.js 22.x
 */

import { Agent, tool } from "@strands-agents/sdk";
import { OpenAIModel } from "@strands-agents/sdk/openai";
import { z } from "zod";

// Agent is created once outside the handler — reused on warm invocations
const model = new OpenAIModel({
  modelId: "claude-sonnet-4",
  apiKey: process.env.LITELLM_API_KEY ?? "sk-local",
  clientConfig: {
    baseURL: process.env.LITELLM_BASE_URL ?? "http://localhost:4000",
  },
});

const greet = tool({
  name: "greet",
  description: "Generate a friendly greeting for a given name.",
  inputSchema: z.object({
    name: z.string().describe("The person's name"),
  }),
  callback: ({ name }) => `Hello, ${name}! Welcome to Strands on Lambda.`,
});

const agent = new Agent({
  model,
  tools: [greet],
  systemPrompt: "You are a friendly greeter. Always use the greet tool when given a name.",
  printer: false,
});

// ─── Lambda event types ───────────────────────────────────────────────────────
interface LambdaEvent {
  body?: string;
  message?: string;
}

interface LambdaResponse {
  statusCode: number;
  headers: Record<string, string>;
  body: string;
}

// ─── Handler ──────────────────────────────────────────────────────────────────
export const handler = async (event: LambdaEvent): Promise<LambdaResponse> => {
  const rawBody = event.body ?? event.message ?? "";
  const message = typeof rawBody === "string" ? rawBody : JSON.stringify(rawBody);

  if (!message) {
    return {
      statusCode: 400,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: "Missing message in request body or event.message" }),
    };
  }

  const result = await agent.invoke(message);

  return {
    statusCode: 200,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ response: result.toString() }),
  };
};

// ─── Local test (run directly with tsx) ──────────────────────────────────────
const testEvent: LambdaEvent = { message: "Please greet Alice." };
const response = await handler(testEvent);
console.log("Lambda response:", JSON.parse(response.body));
