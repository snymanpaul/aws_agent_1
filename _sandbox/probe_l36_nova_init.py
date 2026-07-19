"""
Probe: Nova Sonic start() initialization and audio flow.
Does it require audio input or can it work text-only?
"""
import inspect, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel

src = inspect.getsource(BidiNovaSonicModel)
lines = src.split('\n')

# Print start() method
print("=== start() method ===")
in_start = False
indent = 0
for i, line in enumerate(lines):
    if '    async def start(' in line:
        in_start = True
        indent = len(line) - len(line.lstrip())
    if in_start:
        print(f"{i:4}: {line}")
        # stop at next method at same indent level
        if i > 0 and line.strip() and not line.strip().startswith('#') and len(line) - len(line.lstrip()) <= indent and i > 100:
            if line.strip().startswith('async def') or line.strip().startswith('def '):
                break

# Print _get_session_start_event and init events
print("\n=== _get_session_start and audio config ===")
for i, line in enumerate(lines):
    if ('session' in line.lower() or 'NOVA_AUDIO' in line or 'audioInput' in line or
        '_start_event' in line or 'promptStart' in line):
        print(f"{i:4}: {line}")

# Print NOVA_AUDIO constants
print("\n=== NOVA_AUDIO constants ===")
for i, line in enumerate(lines[:30]):
    print(f"{i:4}: {line}")

# Check module-level constants
print("\n=== Module-level constants ===")
import strands.experimental.bidi.models.nova_sonic as ns_mod
for name in dir(ns_mod):
    if 'NOVA' in name or 'AUDIO' in name or 'DEFAULT' in name or 'CONFIG' in name:
        print(f"  {name} = {getattr(ns_mod, name)}")
