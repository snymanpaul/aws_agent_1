"""
Probe: Read Skill, AgentSkills source to understand the API.

Run: uv run python 11_platform/_sandbox/probe_skills_source.py
"""

import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strands.vended_plugins.skills import AgentSkills, Skill, SkillSource, SkillSources

print("=== Skill ===")
print(inspect.getsource(Skill))

print("\n=== AgentSkills ===")
print(inspect.getsource(AgentSkills))

print("\n=== SkillSource ===")
try:
    print(inspect.getsource(SkillSource))
except Exception as e:
    print(f"  {type(e).__name__}: {e}")

print("\n=== SkillSources ===")
try:
    print(inspect.getsource(SkillSources))
except Exception as e:
    print(f"  {type(e).__name__}: {e}")
