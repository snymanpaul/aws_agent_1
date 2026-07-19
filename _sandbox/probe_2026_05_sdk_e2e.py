"""
Experiment 3 (offline): test new v1.36-1.38 SDK features without LLM calls.
"""

import sys, os, inspect, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.models.openai import OpenAIModel


async def main():
    print("=" * 70)
    print("3a: count_tokens (offline, tiktoken-based)")
    print("=" * 70)

    model = OpenAIModel(
        model_id="claude-sonnet-4",
        client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
    )

    short = [{"role": "user", "content": [{"text": "What is the capital of France?"}]}]
    n = await model.count_tokens(messages=short, system_prompt="You are concise.")
    print(f"  short query: {n} tokens")

    big = [{"role": "user", "content": [{"text": "X" * 10000}]}]
    n_big = await model.count_tokens(messages=big)
    print(f"  10k 'X' chars: {n_big} tokens (chars/4 ~ 2500)")

    print("\n" + "=" * 70)
    print("3b: take_snapshot / load_snapshot")
    print("=" * 70)

    agent = Agent(model=model, callback_handler=None, system_prompt="You are a test.")
    agent.messages.append({"role": "user", "content": [{"text": "Hello"}]})
    agent.messages.append({"role": "assistant", "content": [{"text": "Hi there"}]})
    print(f"  initial: {len(agent.messages)} messages")

    snap = agent.take_snapshot(preset="session")
    print(f"  snapshot type: {type(snap).__name__}")
    print(f"  all public attrs: {[a for a in dir(snap) if not a.startswith('_')]}")
    if hasattr(snap, "model_fields"):
        print(f"  pydantic fields: {list(snap.model_fields.keys())}")

    agent.messages.append({"role": "user", "content": [{"text": "Drift!"}]})
    print(f"  after mutation: {len(agent.messages)} messages")

    agent.load_snapshot(snap)
    print(f"  after load_snapshot: {len(agent.messages)} messages (expected 2)")

    snap_msgs = agent.take_snapshot(include=["messages"])
    print(f"  include=['messages'] snapshot: {snap_msgs}")

    snap_app = agent.take_snapshot(preset="session", app_data={"trace_id": "abc"})
    print(f"  app_data: {getattr(snap_app, 'app_data', 'no attr')}")

    print("\n" + "=" * 70)
    print("3c: context_offloader plugin")
    print("=" * 70)
    from strands.vended_plugins.context_offloader import plugin as op, storage as os_
    pcs = [n for n in dir(op) if isinstance(getattr(op, n), type) and not n.startswith('_')]
    scs = [n for n in dir(os_) if isinstance(getattr(os_, n), type) and not n.startswith('_')]
    print(f"  plugin classes: {pcs}")
    print(f"  storage classes: {scs}")
    for cn in pcs:
        cls = getattr(op, cn)
        try:
            print(f"  {cn}.__init__: {inspect.signature(cls.__init__)}")
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("3d: experimental.checkpoint")
    print("=" * 70)
    from strands.experimental.checkpoint import Checkpoint, CheckpointPosition, CHECKPOINT_SCHEMA_VERSION
    print(f"  schema version: {CHECKPOINT_SCHEMA_VERSION}")
    if hasattr(Checkpoint, "model_fields"):
        print(f"  Checkpoint fields: {list(Checkpoint.model_fields.keys())}")
    print(f"  CheckpointPosition: {CheckpointPosition}")

    print("\n" + "=" * 70)
    print("3e: BedrockModel strict_tools")
    print("=" * 70)
    from strands.models.bedrock import BedrockModel
    import strands.models.bedrock as bm
    src = open(bm.__file__).read()
    print(f"  'strict_tools' occurrences: {src.count('strict_tools')}")
    # find the param
    import re
    m = re.search(r'strict_tools[^,\n)]{0,80}', src)
    print(f"  first context: {m.group(0) if m else 'none'}")

    print("\n" + "=" * 70)
    print("3f: agent_core_runtime_client (verify AgentCore connection lib)")
    print("=" * 70)
    try:
        from bedrock_agentcore.runtime.agent_core_runtime_client import AgentCoreRuntimeClient
        print(f"  AgentCoreRuntimeClient signature: {inspect.signature(AgentCoreRuntimeClient.__init__)}")
    except Exception as e:
        print(f"  err: {e}")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())
