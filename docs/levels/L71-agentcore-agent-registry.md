# L71: AgentCore Agent Registry — Publish & Discover an `AGENT_SKILLS` Bundle

**Code:** `15_agentcore_registry/agent_registry.py`
**Reflection:** [`level-71-reflection.md`](../../.claude/learnings/reflections/level-71-reflection.md)

**Status:** Done (Tier 20, live AWS; self-tearing-down).

**Empirical findings (live-validated):**
- The Registry is a unified governed catalog: `DescriptorType` ∈ `MCP | A2A | CUSTOM | AGENT_SKILLS`;
  control plane `bedrock-agentcore-control`, data plane `bedrock-agentcore` (`SearchRegistryRecords`).
  Realizes the 2026-05-19 registry note (`NOTE_2026-05-19_agentcore_agent_registry.md`).
- **Approval gates discovery**: `SearchRegistryRecords` returns ONLY `APPROVED` records — the same
  query is empty while the record is `DRAFT`, found once `APPROVED`.
- `create_registry`/`delete_registry` are async (202; `CREATING`→`READY`→`DELETING`);
  `skillMd.inlineContent` must be `---`-frontmatter SKILL.md; search is eventually consistent
  (~8–12 s post-approval).
- Pairs with L30 (local Strands `AgentSkills`): L30 runs a skill in-process; L71 publishes, governs,
  and discovers one org-wide.
