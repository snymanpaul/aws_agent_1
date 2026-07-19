"""Probe: Nova Sonic _convert_nova_event to find BidiResponseCompleteEvent emission."""
import inspect, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel

print("=== _convert_nova_event ===")
src = inspect.getsource(BidiNovaSonicModel._convert_nova_event)
print(src)
