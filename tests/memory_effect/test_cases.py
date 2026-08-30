"""Offline controls for the twenty A5 verifiers: one wrong, one right, one not-applicable.

Every row is written from the observation's own text. A verifier that cannot tell the
recorded mistake from its correction cannot measure whether the memory helped, and a verifier
that scores an answer which never reached the fork would move the rate for a reason that has
nothing to do with memory.

These also prove the twenty cited observations are still in the log, so a case can never
quietly drift away from the entry it claims to test.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cases import CASES, note_for  # noqa: E402

BY_KEY = {c["key"]: c for c in CASES}

# key, an answer that REPEATS the mistake, an answer that avoids it, an answer that never
# reached the fork.
CONTROLS = [
    ("C01_SESSIONS",
     'manager = FileSessionManager(storage_dir="./sessions")\n'
     'agent = Agent(model=model, session_id="demo")',
     'manager = FileSessionManager(session_id="demo", storage_dir="./sessions")\n'
     'agent = Agent(model=model, session_manager=manager)',
     "Persist the conversation to disk between runs."),
    ("C02_SWARM",
     "swarm = Swarm(agents=[coder, reviewer])",
     "swarm = Swarm([coder, reviewer], max_handoffs=6)",
     "Build a team of two agents that hand work to each other."),
    ("C03_GRAPH",
     "graph = GraphBuilder().build(max_iterations=10)",
     "builder = GraphBuilder()\nbuilder.set_max_node_executions(10)\ngraph = builder.build()",
     "Wire two agents in sequence."),
    ("C04_MCP_TOOL_USE_ID",
     'client.call_tool_sync(name="search", arguments={"q": "strands"})',
     'client.call_tool_sync(tool_use_id="1", name="search", arguments={"q": "strands"})',
     "First list the tools the server exposes."),
    ("C05_MCP_URL",
     '{"url": "http://localhost:8000/mcp"}',
     '{"url": "http://localhost:8000/mcp/"}',
     '{"command": "npx", "args": ["-y", "server-fetch"]}'),
    ("C06_NEST_ASYNCIO",
     "loop = asyncio.get_event_loop()\nreturn loop.run_until_complete(fetch(city))",
     "import nest_asyncio\nnest_asyncio.apply()\n"
     "return asyncio.get_event_loop().run_until_complete(fetch(city))",
     "Call the async client from an async tool with await."),
    ("C07_PYDANTIC",
     'class Reply(BaseModel):\n    text: str\n\n    class Config:\n        extra = "allow"',
     'class Reply(BaseModel):\n    text: str\n    model_config = {"extra": "allow"}',
     "Return a plain dict from the tool."),
    ("C08_PROXY_AUTH",
     'requests.post("http://localhost:4000/v1/chat/completions", json=payload)',
     'requests.post("http://localhost:4000/v1/chat/completions", json=payload,\n'
     '              headers={"Authorization": "Bearer sk-local"})',
     "Call the provider API directly with the SDK."),
    ("C09_CONTAINER_URL",
     "FROM python:3.13\nENV LITELLM_BASE_URL=http://localhost:4000",
     "FROM python:3.13\nENV LITELLM_BASE_URL=http://host.docker.internal:4000",
     "Run the agent locally with uv and no container."),
    ("C10_TOOL_FUNC",
     "@tool\ndef fetch_population(city: str) -> int:\n    ...\n\n"
     "await asyncio.to_thread(fetch_population.func, city)",
     "@tool\ndef fetch_population(city: str) -> int:\n    ...\n\n"
     "await asyncio.to_thread(fetch_population, city)",
     "Call the plain function in a thread."),
    ("C11_STEERING",
     "class Guard(SteeringHandler):\n    def steer(self, ctx):\n        return Block()",
     "class Guard(SteeringHandler):\n    def steer_before_tool(self, ctx):\n        return Block()",
     "Add a hook that logs every tool call."),
    ("C12_AGENT_CARD",
     "card = remote.get_agent_card()\nprint(card.name)",
     "card = asyncio.run(remote.get_agent_card())\nprint(card.name)",
     "Discover the remote agent over HTTP."),
    ("C13_STRUCTURED_OUTPUT",
     "person = agent.structured_output(Person, prompt)",
     "result = agent(prompt, structured_output_model=Person)\nperson = result.structured_output",
     "Ask the agent for JSON and parse it."),
    ("C14_TOOL_CONTEXT",
     "def on_tool_call(ctx):\n    log(ctx.tool_call_args)",
     "def on_tool_call(ctx):\n    log(ctx.tool_name, ctx.tool_input)",
     "Log every tool invocation to stdout."),
    ("C15_AGUI_FIELDS",
     'if event["type"] == "TOOL_CALL_START":\n    print(event["tool_name"])',
     'if event["type"] == "TOOL_CALL_START":\n    print(event["toolCallName"])',
     "Read the SSE stream and print each line."),
    ("C16_S3VECTORS",
     "except s3vectors.exceptions.ResourceNotFoundException:\n    create_index()",
     "except s3vectors.exceptions.NotFoundException:\n    create_index()",
     "Create the bucket if the list call comes back empty."),
    ("C17_TEMPORAL",
     "result = await handle.result(timeout=60)",
     "result = await asyncio.wait_for(handle.result(), timeout=60)",
     "Start the workflow and return its id."),
    ("C18_MCP_TOOL_ATTR",
     "for t in client.list_tools_sync():\n    print(t.name)",
     "for t in client.list_tools_sync():\n    print(t.tool_name, t.mcp_tool.description)",
     "Print how many tools the server exposes."),
    ("C19_SESSION_MESSAGE",
     "rows: list[SessionMessage] = repo.list_messages(session_id)\n"
     "for m in rows:\n    if m.role == 'user':\n        n += 1",
     "rows: list[SessionMessage] = repo.list_messages(session_id)\n"
     "for m in rows:\n    if m.message.get('role') == 'user':\n        n += 1",
     "Count the turns stored on disk."),
    ("C20_METRICS",
     'print(result.metrics.get("inputTokens"))',
     "print(result.metrics.accumulated_usage)",
     "Print the reply text."),
]


@pytest.mark.parametrize("key,wrong,right,not_applicable", CONTROLS)
def test_verifier_separates_the_mistake_from_its_correction(key, wrong, right, not_applicable):
    recurs = BY_KEY[key]["recurs"]
    assert recurs(wrong) is True, f"{key}: the recorded mistake was not detected"
    assert recurs(right) is False, f"{key}: the correction was scored as the mistake"
    assert recurs(not_applicable) is None, f"{key}: an answer that never reached the fork was scored"


@pytest.mark.parametrize("key,wrong,right,not_applicable", CONTROLS)
def test_an_answer_that_explains_the_rule_is_not_a_recurrence(key, wrong, right, not_applicable):
    """The control that changed the design, found in the run's own output.

    A C02_SWARM answer in the memory arm wrote `Swarm([coder, reviewer])`, correctly, and
    added "Note: Swarm expects agents as a positional list argument, e.g. Swarm([a1, a2]),
    not as a keyword like Swarm(agents=[a1, a2])." The first verifier scored that as a
    recurrence. It would have counted the memory arm's habit of restating the memory as
    evidence that the memory does not work, which is the opposite of what the bytes say.
    """
    recurs = BY_KEY[key]["recurs"]
    with_a_note = right + "\n\nNote: do not write " + wrong.replace("\n", " ") + " here."
    assert recurs(with_a_note) is False, f"{key}: an explanation was scored as a recurrence"


def test_every_case_is_controlled():
    assert {c["key"] for c in CASES} == {row[0] for row in CONTROLS}
    assert len(CASES) == 20


def test_every_case_cites_an_observation_that_is_in_the_log():
    for case in CASES:
        assert note_for(case["obs_id"]).strip(), case["obs_id"]


# The token that would hand the answer to the model. A task containing one of these would
# measure instruction repetition rather than whether the captured memory was used.
GIVEAWAYS = {
    "C01_SESSIONS": ["session_manager", "FileSessionManager(session_id"],
    "C02_SWARM": ["Swarm(["],
    "C03_GRAPH": ["set_max_node_executions"],
    "C04_MCP_TOOL_USE_ID": ["tool_use_id"],
    "C05_MCP_URL": ["/mcp/"],
    "C06_NEST_ASYNCIO": ["nest_asyncio"],
    "C07_PYDANTIC": ["model_config"],
    "C08_PROXY_AUTH": ["Authorization", "Bearer"],
    "C09_CONTAINER_URL": ["host.docker.internal"],
    "C10_TOOL_FUNC": ["_tool_func", ".func"],
    "C11_STEERING": ["steer_before_tool"],
    "C12_AGENT_CARD": ["asyncio.run", "await"],
    "C13_STRUCTURED_OUTPUT": ["structured_output_model"],
    "C14_TOOL_CONTEXT": ["tool_input"],
    "C15_AGUI_FIELDS": ["toolCallName", "camelCase"],
    "C16_S3VECTORS": ["NotFoundException"],
    "C17_TEMPORAL": ["wait_for"],
    "C18_MCP_TOOL_ATTR": ["tool_name"],
    "C19_SESSION_MESSAGE": [".message"],
    "C20_METRICS": ["accumulated_usage", "EventLoopMetrics"],
}


def test_every_case_has_three_paraphrases_that_do_not_hand_over_the_answer():
    assert set(GIVEAWAYS) == {c["key"] for c in CASES}
    for case in CASES:
        assert len(case["tasks"]) == 3, case["key"]
        for task in case["tasks"]:
            for token in GIVEAWAYS[case["key"]]:
                assert token not in task, f"{case['key']}: a task contains {token!r}"
