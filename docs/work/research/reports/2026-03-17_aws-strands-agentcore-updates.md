# AWS Strands Agents SDK & AgentCore Updates (Dec 2025 – Mar 2026)

**Date**: 2026-03-17
**Model**: perplexity/sonar-pro
**Query**: What are the latest updates to AWS Strands Agents SDK and AWS AgentCore since December 2025?
**Coverage**: December 2025 – March 2026

---

## Executive Summary

Since the project's L27 completion in December 2025, both the Strands Agents SDK and AWS Bedrock AgentCore have continued evolving rapidly. The SDK has shipped at least versions v1.25 through v1.29 with major additions including TypeScript GA, MCP Tasks support, concurrent invocation mode, and a new `add_hook` API. AgentCore has delivered three significant GA releases: Policy (March 3), Episodic Memory, and LTM Streaming Notifications (March 12). AWS also launched **Strands Labs** (February 23) as an experimental GitHub org for cutting-edge agentic research.

---

## 1. Strands Agents SDK – Version History (Post-L27)

The SDK was at approximately v0.x during the learning project; by early 2026 it reached v1.27+ with semantic versioning established.

### v1.26.0 (February 11, 2026) [2]
- Added guidance using Protocol instead of Callable for extensible interfaces
- Basic support for Tasks in MCP (Model Context Protocol)
- Various dependency updates and bug fixes

### v1.27.0 (February 19, 2026) [3]
- **`concurrent_invocation_mode` parameter** added to the Agent class — enables parallel tool invocation
- **MCP Tasks support** (basic) — agents can now handle MCP Tasks, not just MCP Resources/Prompts
- **`add_hook` convenience method** added for hook callback registration (simpler than previous API)
- Fixed handling of OpenAI model responses with tool calls
- Upgraded MCP minimum dependency to 1.23.0 for Tasks support
- Added Python 3.14 test coverage
- Bug fixes: exception propagation to `AfterToolCallEvent`, Gemini tool use fixes

### v1.29.0 (latest as of March 2026) [6]
- Full changelog not yet indexed but version confirmed on PyPI Safety database

### Breaking Changes Policy [3]
- SDK uses **strict semantic versioning**: breaking changes only in major releases, always with migration guides
- Exception: "rapidly evolving AI standards" like MCP and A2A protocol may have opt-in breaks in minor versions
- Notable pre-v1.25 breaks (for reference): removed `max_parallel_tools` from Agent (thread pools now), `load_tools_from_directory` defaults to `False`, removed `kwargs` spread in agent calls

---

## 2. TypeScript SDK – General Availability

Announced at re:Invent 2025 (December 3) [1], the TypeScript SDK moved from preview to available:

- **Full type safety** for agent/tool definitions
- **Same `@tool` decorator pattern** — functions with TypeScript doc-comments become agent tools
- **Side-by-side parity** with Python SDK: same multi-agent patterns (Graph, Swarm, Agents-as-Tools)
- Enables Node.js/serverless Lambda deployments of Strands agents natively

---

## 3. Edge Device Support – Generally Available

Also announced December 3, 2025 [1]:

- Agents can now run on **small-scale edge devices** using local models (llama.cpp provider)
- Supports **bidirectional streaming** on edge
- Enables architecture: edge device runs VLA/local model for low-latency; delegates complex reasoning to cloud LLM via AgentCore
- Use case: robotics, IoT, on-premises inference without cloud round-trip for every token

---

## 4. Strands Steering – Experimental Feature

Announced December 3, 2025 [1]:

- **Modular prompting mechanism** that injects feedback to agents at strategic lifecycle points
- Guides agents toward desired outcomes without requiring rigid graph/workflow structures
- Sits between fully freeform (pure Swarm) and fully deterministic (Graph) — dynamic guardrails at runtime
- Status: experimental

---

## 5. New Multi-Agent Patterns and Tools

### Workflow Pattern (New) [5]
Added to `strands-agents-tools` package (not in core SDK):
- Structured flows **without cycles** (unlike Graph which allows cycles)
- Automatic task output capture becomes input for next step
- Use case: linear processing pipelines where order is fixed

### Invocation State (Formalized) [5]
`invocation_state` dict now officially documented as the mechanism for:
- Passing shared state across agents, tools, and hooks
- Keeping configuration hidden from LLM prompts (security/prompt hygiene)
- Thread-safe sharing in parallel agent execution

### 12+ Model Providers [7]
Framework now officially supports 12+ model providers including:
- Amazon Bedrock (all models), Anthropic, Google Gemini, Ollama, Llama API, llama.cpp, OpenAI-compatible endpoints

---

## 6. AWS AgentCore (Bedrock AgentCore) – New Capabilities

### 6.1 Policy – Generally Available (March 3, 2026) [9][10]

The most significant governance feature to date:

- Define agent boundaries using **natural language policies** (no code required)
- Policies are converted to **Cedar format** automatically for fine-grained enforcement
- **AgentCore Gateway performs real-time checks** at millisecond latency, thousands of requests/second
- Controls what agents can access: APIs, Lambda functions, Salesforce, Slack, other tools
- Example policies: "only access customer data during business hours", "refunds under $100 only"
- Zero impact on agent response latency despite real-time enforcement

### 6.2 AgentCore Memory – Episodic Functionality GA [4][8]

- **Episodic memory** captures structured episodes: context, reasoning, actions, outcomes
- Automated pattern analysis improves agent decision-making over time
- Faster retrieval of relevant historical data for similar tasks
- Example: agent learns user prefers 30-min early pickup after 5 successful trips, applies automatically

### 6.3 AgentCore Memory – LTM Streaming Notifications (March 12, 2026) [11]

Very recent addition (5 days before this report):

- **Push notifications via Amazon Kinesis** when long-term memory records are created or modified
- Eliminates polling — event-driven memory updates
- Enables real-time workflows, state refreshes, and audit trails
- Use cases: personalized experience updates, compliance logging, cross-agent memory sync

### 6.4 AgentCore Evaluations [4][8]

- **13 pre-built evaluators**: correctness, helpfulness, tool selection, safety, goal success, context relevance
- Support for **custom evaluators** using LLMs
- Continuously samples live interactions (not just test sets)
- CloudWatch integration: dashboards for tokens, latency, error rates
- Alert configuration: e.g., trigger alert when satisfaction score drops 10%
- OpenTelemetry integration for distributed tracing across agent chains

### 6.5 AgentCore Runtime – Production Features Confirmed [4]
- 8-hour session isolation (long-running agent support)
- Identity management integration with existing providers (SSO, Cognito)
- OpenTelemetry native tracing
- No new runtime-specific features announced Jan-Mar 2026 (stable)

---

## 7. Strands Labs – Launched February 23, 2026

AWS launched **Strands Labs** as a separate GitHub organization for experimental, state-of-the-art agentic development [13][14][15]:

### 7.1 Robots Project
- Strands Agents interface for **controlling physical robots**
- Integrates with sensors, hardware, vision-language-action (VLA) models
- Integration with NVIDIA GR00T for real-time manipulation tasks (robotic arm)
- Edge Strands agent runs local VLA; cloud Strands agent handles complex reasoning

### 7.2 Robots Sim Project
- **Physics-based 3D simulation environment** for robot behavior prototyping
- Supports Libero benchmarks for VLA policy testing
- Enables debugging and iteration without physical hardware
- Video recording of simulation runs for analysis

### 7.3 AI Functions Project
- `@ai_function` decorator: define **agent behavior in natural language** with Python pre/post-conditions
- Agent loop generates, validates, and self-corrects code implementations
- Example: "parse this CSV and return a Pandas DataFrame with columns X, Y, Z" — agent writes and validates the code
- Built-in guardrails: controlled code execution, restricted imports
- Reduces boilerplate for dynamic tool creation (builds on L24 Tool Synthesis patterns)

---

## 8. Additional Ecosystem Updates

### Llama 4 Multi-Agent Integration (January 21, 2026) [16]
- AWS blog post demonstrating Strands Agents + Meta Llama 4 multimodal on Bedrock
- Video processing multi-agent workflow using Llama 4's vision capabilities
- Pattern: specialized vision agent + orchestrator agent with `strands-agents-tools`

### "Picking an AI Agent Framework in 2026" (March 15, 2026) [7]
AWS builder center officially positions Strands as:
- Best for: **minimal boilerplate, broad provider support (12+), first-class MCP integration**
- Recommendation: "Something in production on AWS next month → Strands + Bedrock AgentCore"
- Validates the L1-L27 learning path as the right stack for AWS production agents

### A2A Protocol Reference
- Search results hint at A2A (Agent-to-Agent) protocol support in the SDK
- `A2AServerAgentCardURL` mentioned in release notes (minor breaking change in behavior)
- Suggests built-in agent discovery/communication protocol beyond MCP
- Insufficient public docs as of March 2026; likely emerging feature

---

## 9. What Changed vs L1-27 Learning Plan

| Area | L1-27 Status | Post-Dec 2025 Update |
|------|-------------|---------------------|
| TypeScript SDK | Not covered (Python only) | Now GA — new learning track possible |
| Edge deployment | Not covered | GA — llama.cpp on device + cloud delegation |
| Strands Steering | Not covered | Experimental — dynamic lifecycle prompting |
| MCP Tasks | Basic MCP covered (L9) | Tasks support added in v1.27 |
| `concurrent_invocation_mode` | Not covered | New Agent parameter for parallel tools |
| `add_hook` API | Hooks mentioned (L21) | Simpler `add_hook` convenience method |
| AgentCore Policy | Not covered | GA — Cedar-format natural language policies |
| AgentCore Episodic Memory | LTM memory covered (L14-17) | GA structured episodes with pattern learning |
| AgentCore LTM Streaming | Not covered | Kinesis-push notifications (very new) |
| AgentCore Evaluations | Observability (L21) | 13 pre-built evaluators, live sampling |
| Strands Labs: AI Functions | Tool Synthesis (L24) | @ai_function decorator is a simpler pattern |
| Strands Labs: Robots | Not covered | Entirely new domain (physical/embodied AI) |
| Workflow pattern | Graph + Swarm covered (L6-8) | New Workflow tool (no-cycle linear flows) |

---

## 10. Recommended Next Learning Levels (L28+)

Based on the post-L27 updates, these are the highest-value new areas:

### L28: TypeScript SDK Parity
- Build same agent patterns in TypeScript
- Compare Python vs TypeScript for Lambda deployment
- Key learning: when to choose each

### L29: AgentCore Policy (Governance Layer)
- Natural language policy authoring
- Cedar format integration
- Policy testing with Gateway simulation

### L30: AgentCore Evaluations in Production
- Configure 13 pre-built evaluators
- Build custom evaluators
- CloudWatch alerts on quality metrics

### L31: MCP Tasks + Concurrent Invocation
- MCP Tasks pattern vs MCP Resources/Prompts
- `concurrent_invocation_mode` for parallel tool execution
- `add_hook` patterns for lifecycle observability

### L32: Strands Labs – AI Functions
- `@ai_function` decorator pattern
- Compare with L24 Tool Synthesis (complexity vs simplicity)
- Security model for dynamic code generation

### L33: AgentCore LTM Streaming + Kinesis
- Event-driven memory update patterns
- Real-time agent personalization pipeline
- Kinesis consumer for memory audit trails

### L34: Edge Strands + Cloud Orchestration
- llama.cpp provider configuration
- Edge-to-cloud delegation pattern
- Bidirectional streaming on constrained devices

---

## Sources

[1] https://aws.amazon.com/about-aws/whats-new/2025/12/typescript-strands-agents-preview/ — "Announcing TypeScript support in Strands Agents (preview) and more"
[2] https://newreleases.io/project/github/strands-agents/sdk-python/release/v1.26.0 — "strands-agents/sdk-python v1.26.0 on GitHub"
[3] https://newreleases.io/project/github/strands-agents/sdk-python/release/v1.27.0 — "strands-agents/sdk-python v1.27.0 on GitHub"
[4] https://www.aboutamazon.com/news/aws/aws-amazon-bedrock-agent-core-ai-agents — "New Amazon Bedrock AgentCore capabilities"
[5] https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/ — "Multi-agent Patterns - Strands Agents SDK"
[6] https://data.safetycli.com/packages/pypi/strands-agents/changelog — "strands-agents Changelog - Safety CLI"
[7] https://builder.aws.com/content/3AzsgG6TreTO3uLRqpWNxfEyUhe/picking-an-ai-agent-framework-in-2026 — "Picking an AI Agent Framework in 2026 - AWS Builder Center"
[8] https://aws.amazon.com/bedrock/agentcore/ — "Amazon Bedrock AgentCore - AWS"
[9] https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/ — "Policy in Amazon Bedrock AgentCore is now generally available"
[10] https://awsinsider.net/blogs/awsinsider-release-radar/2026/03/amazon-bedrock-agentcore.aspx — "Amazon Bedrock AgentCore Policy Reaches General Availability"
[11] https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-memory-streaming-ltm/ — "Amazon Bedrock AgentCore Memory announces streaming notifications for LTM"
[12] https://aws.amazon.com/blogs/aws/aws-weekly-roundup-amazon-connect-health-bedrock-agentcore-policy-gameday-europe-and-more-march-9-2026/ — "AWS Weekly Roundup March 9, 2026"
[13] https://aws.amazon.com/blogs/opensource/introducing-strands-labs-get-hands-on-today-with-state-of-the-art-experimental-approaches-to-agentic-development/ — "Introducing Strands Labs"
[14] https://www.infoq.com/news/2026/03/aws-strands-agents/ — "AWS Launches Strands Labs for Experimental AI Agent Projects" (InfoQ, March 11, 2026)
[15] https://www.computerweekly.com/blog/CW-Developer-Network/AWS-extends-hands-on-experimental-agentic-development-with-Strands-Labs — "AWS extends hands-on experimental agentic development with Strands Labs"
[16] https://aws.amazon.com/blogs/machine-learning/using-strands-agents-to-create-a-multi-agent-solution-with-metas-llama-4-and-amazon-bedrock/ — "Using Strands Agents with Meta's Llama 4 and Amazon Bedrock" (January 21, 2026)
[17] https://strandsagents.com/latest/documentation/docs/user-guide/versioning-and-support/ — "Versioning & Support - Strands Agents SDK"
[18] https://pub.towardsai.net/operationalizing-agentic-ai-on-aws-a-2026-architects-guide-12873e967c30 — "Operationalizing Agentic AI on AWS: A 2026 Architect's Guide"
