"""
L41 Probe: Custom Orchestration API in Strands
Goal: understand how to override/replace the default ReAct loop

Questions to answer:
1. What is the custom orchestrator interface? (class, protocol, callable?)
2. How does it plug into Agent? (constructor param? subclass? plugin?)
3. What does _run_loop do vs _execute_event_loop_cycle?
4. Is there an `orchestrator` param on Agent?
5. What events/hooks are available for intercepting tool calls?
6. What does the event_loop module expose?
"""
import inspect
import strands
from strands import Agent
from strands.agent import agent as agent_module

print("=" * 60)
print("1. Agent __init__ params (orchestration-related)")
print("=" * 60)
sig = inspect.signature(Agent.__init__)
for name, param in sig.parameters.items():
    if name in ('tool_executor', 'hooks', 'plugins', 'retry_strategy'):
        print(f"  {name}: {param.annotation} = {param.default!r}")

print()
print("=" * 60)
print("2. _execute_event_loop_cycle signature")
print("=" * 60)
print(inspect.signature(Agent._execute_event_loop_cycle))

print()
print("=" * 60)
print("3. event_loop module contents")
print("=" * 60)
import strands.event_loop as el
for name in sorted(dir(el)):
    if not name.startswith('__'):
        print(f"  {name}")

print()
print("=" * 60)
print("4. ToolExecutor interface")
print("=" * 60)
try:
    from strands.tools.executors import _executor
    for name in dir(_executor):
        if not name.startswith('__'):
            obj = getattr(_executor, name)
            if inspect.isclass(obj):
                print(f"  class {name}")
                print(f"    methods: {[m for m in dir(obj) if not m.startswith('_')]}")
except Exception as e:
    print(f"  error: {e}")

print()
print("=" * 60)
print("5. Hooks available")
print("=" * 60)
try:
    import strands.hooks as hooks_mod
    for name in sorted(dir(hooks_mod)):
        if not name.startswith('__'):
            print(f"  {name}")
except Exception as e:
    print(f"  error: {e}")

print()
print("=" * 60)
print("6. strands.event_loop submodules")
print("=" * 60)
import pkgutil
import strands.event_loop as el_pkg
for mod in pkgutil.iter_modules(el_pkg.__path__):
    print(f"  {mod.name}")
