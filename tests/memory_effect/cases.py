"""A5: twenty captured mistakes, each with the task that produced it and a verifier.

The unit of measurement here is the OBSERVATION, not the level. For each case:

    obs_id    the entry in .claude/learnings/observations.jsonl. Its text is loaded from the
              log at run time, never retyped here, so the arm that carries the memory carries
              exactly what was captured.
    tasks     three paraphrases (R5) that recreate the situation the mistake happened in,
              WITHOUT stating the correction. Each names the API surface concretely so the
              answer has a chance to reach the same fork; none of them names the right call.
    recurs    True when the mistake RECURRED in the answer, False when it did not, and None
              when the answer never reached the fork. The rate is computed over runs that
              reached the fork, because an answer that never touched the API can neither
              repeat the mistake nor avoid it.

SELECTION. The 172 `cat: mistake` entries were walked in id order and 20 were taken across
the full level range, L5 to L58, one per topic area, subject to one eligibility rule stated
up front: the mistake has to be visible in a produced artifact. "The account in todo.md was
wrong" is a real captured mistake and cannot be measured this way. That filter is a limit on
what this experiment can see, not a claim that the rest do not matter.

Each verifier is pinned by a positive and a negative control in `test_cases.py`, both written
from the observation's own text.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOG = ROOT / ".claude" / "learnings" / "observations.jsonl"


def note_for(obs_id: str) -> str:
    """The captured observation, verbatim from the log. Raises if the id is not there."""
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("id") == obs_id:
            return f"{entry['obs']}"
    raise KeyError(f"{obs_id} is not in {LOG.name}")


def _search(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.S))


# Each verifier answers one question: did the answer take the wrong fork the log recorded?
# `None` means it never reached the fork.

def sessions(text: str):
    if "SessionManager" not in text:
        return None
    return _search(r"Agent\([^)]{0,240}session_id", text)


def swarm_positional(text: str):
    if "Swarm(" not in text:
        return None
    return _search(r"Swarm\(\s*agents\s*=", text)


def graph_limits(text: str):
    if "GraphBuilder" not in text:
        return None
    return _search(r"\.build\(\s*[a-z_]*max_", text)


def mcp_tool_use_id(text: str):
    if "call_tool_sync(" not in text:
        return None
    call = re.search(r"call_tool_sync\((.{0,200}?)\)", text, re.S)
    return bool(call) and "tool_use_id" not in call.group(1)


def mcp_trailing_slash(text: str):
    urls = re.findall(r"https?://[^\s\"']*/mcp/?", text)
    if not urls:
        return None
    return any(not u.endswith("/") for u in urls)


def nested_asyncio(text: str):
    if "run_until_complete" not in text:
        return None
    return "nest_asyncio" not in text


def pydantic_config(text: str):
    if "BaseModel" not in text:
        return None
    return _search(r"class Config\b", text)


def litellm_auth(text: str):
    if not _search(r"(localhost|127\.0\.0\.1):4000", text):
        return None
    return not _search(r"Authorization|api_key|API_KEY|Bearer", text)


def container_host_url(text: str):
    # A Dockerfile need not contain the word "docker", so the instruction keywords count too.
    if not _search(r"(?im)docker|container|compose|podman|^\s*(FROM|ENV)\s", text):
        return None
    if not _search(r":4000", text):
        return None
    return "host.docker.internal" not in text


def tool_func_attr(text: str):
    if "@tool" not in text:
        return None
    return _search(r"\w+\.func\b", text)


def steering_method(text: str):
    if "SteeringHandler" not in text:
        return None
    return _search(r"def steer\s*\(", text) and "def steer_before_tool" not in text


def agent_card_await(text: str):
    if "get_agent_card" not in text:
        return None
    return not _search(r"(await|asyncio\.run\()[^\n]{0,80}get_agent_card", text)


def structured_output_call(text: str):
    if "structured_output" not in text:
        return None
    return _search(r"\.structured_output\s*\(", text)


def tool_context_fields(text: str):
    if not _search(r"ToolCallContext|ctx\.tool", text):
        return None
    return _search(r"tool_call_args|ctx\.state\b", text)


def agui_camel_case(text: str):
    if "TOOL_CALL_START" not in text:
        return None
    return _search(r"[\"']tool_name[\"']|[\"']tool_call_id[\"']|\.tool_name\b", text)


def s3vectors_exception(text: str):
    if not _search(r"(?i)s3vectors|s3_vectors", text):
        return None
    return "ResourceNotFoundException" in text


def temporal_result_timeout(text: str):
    if not _search(r"\.result\s*\(", text):
        return None
    return _search(r"\.result\(\s*timeout\s*=", text)


def mcp_tool_name_attr(text: str):
    if "list_tools_sync" not in text:
        return None
    return _search(r"\b\w+\.name\b", text) and not _search(r"\.tool_name\b", text)


def session_message_role(text: str):
    if "SessionMessage" not in text:
        return None
    return _search(r"\.role\b", text) and not _search(r"\.message[\.\[]|\.message\b", text)


def metrics_as_dict(text: str):
    if "metrics" not in text:
        return None
    return _search(r"metrics\.get\(|metrics\[", text)


CASES = [
    dict(obs_id="obs-0014", key="C01_SESSIONS", recurs=sessions, tasks=[
        "Write the Strands code that gives an Agent file-backed session persistence with "
        "FileSessionManager, storing sessions under ./sessions for the session id 'demo'.",
        "Show how to make a Strands Agent remember a conversation across restarts using "
        "strands.session.FileSessionManager with a session id of 'demo'.",
        "Give me the smallest Strands example that wires FileSessionManager into an Agent so "
        "the conversation for session 'demo' survives a restart.",
    ]),
    dict(obs_id="obs-0024", key="C02_SWARM", recurs=swarm_positional, tasks=[
        "Write the Strands code that builds a Swarm of two agents, a coder and a reviewer, "
        "using strands.multiagent.Swarm, and runs it on one task.",
        "Give me a minimal strands.multiagent.Swarm with a researcher agent and a writer "
        "agent, then invoke it.",
        "Show how to construct a Strands Swarm over three agents and call it with a prompt.",
    ]),
    dict(obs_id="obs-0032", key="C03_GRAPH", recurs=graph_limits, tasks=[
        "Write the Strands GraphBuilder code for a two-node graph with a safety limit of 10 "
        "node executions, then build and run it.",
        "Using strands.multiagent.GraphBuilder, wire two agents in sequence and cap how many "
        "node executions the graph may perform.",
        "Give me a Strands graph workflow with GraphBuilder that will not run more than 10 "
        "node executions.",
    ]),
    dict(obs_id="obs-0101", key="C04_MCP_TOOL_USE_ID", recurs=mcp_tool_use_id, tasks=[
        "Write the Strands code that calls one tool on an MCP server synchronously through "
        "MCPClient.call_tool_sync.",
        "Show how to invoke an MCP tool named 'search' with arguments through a Strands "
        "MCPClient using its synchronous call.",
        "Give me the snippet that calls call_tool_sync on a Strands MCPClient for the tool "
        "'fetch' with a url argument.",
    ]),
    dict(obs_id="obs-0121", key="C05_MCP_URL", recurs=mcp_trailing_slash, tasks=[
        "Write the .mcp.json entry for a streamable-http MCP server running locally on port "
        "8000 at its mcp endpoint.",
        "Give me the MCP client config that points at a local MCP server on "
        "http://localhost:8000 using the streamable http transport.",
        "What URL and config does a Strands MCPClient need for a local MCP server listening "
        "on port 8000 at the mcp path?",
    ]),
    dict(obs_id="obs-0139", key="C06_NEST_ASYNCIO", recurs=nested_asyncio, tasks=[
        "Write a Strands @tool that has to call an async function internally, using "
        "asyncio.get_event_loop().run_until_complete, so an agent can call it.",
        "I have an async client and need to expose it as a synchronous Strands tool that the "
        "agent calls. Write it using run_until_complete.",
        "Show a Strands tool function that wraps an async coroutine with "
        "get_event_loop().run_until_complete so it can be used by an agent.",
    ]),
    dict(obs_id="obs-0187", key="C07_PYDANTIC", recurs=pydantic_config, tasks=[
        "Write a Pydantic model for an agent response that allows extra fields.",
        "Give me a Pydantic BaseModel with two fields that tolerates unknown keys in the "
        "input.",
        "Write a Pydantic schema for a tool result that permits additional properties.",
    ]),
    dict(obs_id="obs-0283", key="C08_PROXY_AUTH", recurs=litellm_auth, tasks=[
        "Write the Python that posts one chat completion request to our LiteLLM proxy at "
        "http://localhost:4000 with the requests library.",
        "Show the curl-equivalent Python call to the local LiteLLM proxy on port 4000 for a "
        "chat completion.",
        "Give me the raw HTTP call, in Python, that asks the LiteLLM proxy at localhost:4000 "
        "for one completion.",
    ]),
    dict(obs_id="obs-0319", key="C09_CONTAINER_URL", recurs=container_host_url, tasks=[
        "Write the Dockerfile and env settings for an agent container that must call the "
        "LiteLLM proxy running on the host machine at port 4000.",
        "My agent runs in a Docker container and the LiteLLM proxy runs on the host on port "
        "4000. Give me the environment configuration the container needs.",
        "Write the docker run command and env var for a containerised agent that reaches a "
        "host-side LiteLLM proxy on port 4000.",
    ]),
    dict(obs_id="obs-0337", key="C10_TOOL_FUNC", recurs=tool_func_attr, tasks=[
        "I have a Strands @tool function and want to run it in a thread with "
        "asyncio.to_thread. Write that call.",
        "Show how to call a Strands @tool-decorated function directly from Python, outside "
        "an agent, including from a thread pool.",
        "Write the code that invokes a @tool decorated Strands function concurrently for "
        "three inputs.",
    ]),
    dict(obs_id="obs-0348", key="C11_STEERING", recurs=steering_method, tasks=[
        "Write a Strands SteeringHandler subclass for strands-agents 1.30 that blocks a "
        "risky tool before it runs.",
        "Using the Strands steering API in v1.30, write the handler that intercepts a tool "
        "call and refuses it.",
        "Give me a SteeringHandler for strands-agents 1.30 that guides the model away from "
        "calling a dangerous tool.",
    ]),
    dict(obs_id="obs-0368", key="C12_AGENT_CARD", recurs=agent_card_await, tasks=[
        "Write the code that fetches a remote A2A agent's card through Strands A2AAgent and "
        "prints its name.",
        "Show how to discover a remote agent over A2A with Strands and read the agent card's "
        "name field.",
        "Give me the snippet that connects to an A2A endpoint with Strands and prints the "
        "discovered agent card name.",
    ]),
    dict(obs_id="obs-0475", key="C13_STRUCTURED_OUTPUT", recurs=structured_output_call, tasks=[
        "Write the Strands code that gets a typed Pydantic object back from an agent for a "
        "given prompt.",
        "Show how to make a Strands Agent return a structured Pydantic model instead of free "
        "text.",
        "Give me the Strands call that produces a validated Pydantic instance from one "
        "prompt.",
    ]),
    dict(obs_id="obs-0501", key="C14_TOOL_CONTEXT", recurs=tool_context_fields, tasks=[
        "Write the AG-UI hook for Strands that reads the tool name and the tool arguments "
        "out of a ToolCallContext.",
        "In a Strands AG-UI integration, show the handler that logs which tool was called "
        "and with what arguments from the ToolCallContext.",
        "Give me the code that pulls the arguments dict out of a Strands ToolCallContext "
        "inside a tool-call hook.",
    ]),
    dict(obs_id="obs-0502", key="C15_AGUI_FIELDS", recurs=agui_camel_case, tasks=[
        "Write the Python that consumes an AG-UI SSE stream and prints the tool name from "
        "each TOOL_CALL_START event.",
        "Show how to read TOOL_CALL_START events off an AG-UI event stream and log which "
        "tool started.",
        "Give me the consumer loop for AG-UI events that reports the name and id on every "
        "TOOL_CALL_START.",
    ]),
    dict(obs_id="obs-0509", key="C16_S3VECTORS", recurs=s3vectors_exception, tasks=[
        "Write the boto3 code that creates an S3 Vectors index if it does not already exist, "
        "handling the not-found case.",
        "Using the s3vectors boto3 client, show an idempotent create for a vector bucket "
        "that catches the missing-resource error.",
        "Give me the S3 Vectors setup function that checks for an index and creates it, "
        "catching the exception raised when it is absent.",
    ]),
    dict(obs_id="obs-0578", key="C17_TEMPORAL", recurs=temporal_result_timeout, tasks=[
        "Write the temporalio client code that starts a workflow and waits at most 60 "
        "seconds for its result.",
        "Show how to put a deadline on waiting for a Temporal workflow result from a "
        "WorkflowHandle.",
        "Give me the Python that starts a Temporal workflow and gives up if the result has "
        "not arrived in a minute.",
    ]),
    dict(obs_id="obs-0675", key="C18_MCP_TOOL_ATTR", recurs=mcp_tool_name_attr, tasks=[
        "Write the code that lists the tools an MCP server exposes through a Strands "
        "MCPClient and prints each tool's name and description.",
        "Show how to enumerate MCP tools with list_tools_sync in Strands and log what each "
        "one is called.",
        "Give me the snippet that prints every tool returned by a Strands MCP client's "
        "synchronous tool listing.",
    ]),
    dict(obs_id="obs-0680", key="C19_SESSION_MESSAGE", recurs=session_message_role, tasks=[
        "Write a custom Strands session repository method that counts how many stored "
        "messages came from the user.",
        "Show how to read the role of each stored message from Strands SessionMessage "
        "objects in a session repository.",
        "Give me the code that walks the messages in a Strands session and separates user "
        "turns from assistant turns.",
    ]),
    dict(obs_id="obs-0682", key="C20_METRICS", recurs=metrics_as_dict, tasks=[
        "Write the Strands code that prints the input and output token usage after an agent "
        "call, from the result object.",
        "Show how to read token counts off the result of a Strands agent invocation.",
        "Give me the snippet that reports how many tokens a Strands agent call consumed, "
        "using the returned result.",
    ]),
]
