"""
L44 Probe: ToolCallContext and ToolResultContext field names.
"""
import inspect
from ag_ui_strands import ToolCallContext, ToolResultContext, ToolBehavior

print("=== ToolCallContext fields ===")
print(list(ToolCallContext.model_fields.keys()) if hasattr(ToolCallContext, 'model_fields') else "no model_fields")
print(inspect.signature(ToolCallContext.__init__))
print(dir(ToolCallContext))

print("\n=== ToolResultContext fields ===")
print(list(ToolResultContext.model_fields.keys()) if hasattr(ToolResultContext, 'model_fields') else "no model_fields")
print(inspect.signature(ToolResultContext.__init__))
print(dir(ToolResultContext))
